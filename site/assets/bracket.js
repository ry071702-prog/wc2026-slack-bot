document.addEventListener("DOMContentLoaded", async () => {
  "use strict";

  const app = window.SiteApp;
  const container = document.querySelector("#bracket");
  const roundsNav = document.querySelector("#bracket-rounds");

  const LIVE_STATUSES = new Set(["IN_PLAY", "PAUSED"]);

  // 勝ち上がりツリーを左右に分割し、中央へ決勝が収束する形に並べる。
  // 各列の試合番号は「上から下」の表示順 (ペアが次ラウンドへ繋がる順序)。
  const LEFT_COLS = [
    { stage: "LAST_32", label: "ラウンド32", nos: [74, 77, 73, 75, 83, 84, 81, 82] },
    { stage: "LAST_16", label: "ラウンド16", nos: [89, 90, 93, 94] },
    { stage: "QUARTER_FINALS", label: "準々決勝", nos: [97, 98] },
    { stage: "SEMI_FINALS", label: "準決勝", nos: [101] },
  ];
  const RIGHT_COLS = [
    { stage: "SEMI_FINALS", label: "準決勝", nos: [102] },
    { stage: "QUARTER_FINALS", label: "準々決勝", nos: [99, 100] },
    { stage: "LAST_16", label: "ラウンド16", nos: [91, 92, 95, 96] },
    { stage: "LAST_32", label: "ラウンド32", nos: [76, 78, 79, 80, 86, 88, 85, 87] },
  ];
  // ナビ用タブ (PC=該当列へスクロール / スマホ=該当ラウンドへ切替)
  const ROUND_TABS = [
    { label: "ラウンド32", target: "bk-left-LAST_32", stage: "LAST_32" },
    { label: "ラウンド16", target: "bk-left-LAST_16", stage: "LAST_16" },
    { label: "準々決勝", target: "bk-left-QUARTER_FINALS", stage: "QUARTER_FINALS" },
    { label: "準決勝", target: "bk-left-SEMI_FINALS", stage: "SEMI_FINALS" },
    { label: "決勝", target: "bk-center", stage: "FINAL" },
  ];
  let nodeByNo = new Map();
  let scheduleData = null;
  let ranks = {};
  let proj = null;
  let roundTabButtons = [];

  try {
    const [bracket, schedule, rankings] = await Promise.all([
      app.fetchJson("data/bracket.json"),
      app.fetchJson("data/schedule.json").catch(() => null),
      app.fetchJson("data/rankings.json").catch(() => null),
    ]);
    scheduleData = schedule;
    ranks = rankings || {};
    container.setAttribute("aria-busy", "false");
    render(bracket);
  } catch (error) {
    app.logDataError(error);
    app.showLoadError(container);
  }

  // 現在のグループ順位から、未確定の R32 枠を暫定予測する。
  // 1位/2位は各組の現順位を直接、3位8枠は候補グループへの二部マッチングで割り当てる。
  function buildProjection(schedule, matches) {
    const standings = window.SiteStandings;
    if (!standings || !Array.isArray(schedule)) {
      return null;
    }
    const table = standings.computeStandings(schedule);
    const groupRanks = new Map();
    let totalPlayed = 0;
    table.forEach((entry) => {
      const letter = String(entry.group).split("_")[1] || entry.group;
      groupRanks.set(letter, entry.teams);
      totalPlayed += entry.teams.reduce((sum, row) => sum + (row.played || 0), 0);
    });
    if (totalPlayed === 0) {
      return null; // 結果がまだ無ければ予測しない
    }
    const qualifyingThirds = standings
      .rankThirdPlace(table)
      .filter((row) => row.qualifies);
    const thirdSlots = [];
    matches.forEach((node) => {
      ["home", "away"].forEach((which) => {
        const slot = node[which];
        if (slot && slot.type === "third") {
          thirdSlots.push({ key: `${node.match_no}.${which}`, groups: slot.groups || [] });
        }
      });
    });
    const thirdAssign = assignThirds(thirdSlots, qualifyingThirds);

    // 全体で同じ国が二度出ないよう、確定チームを優先しつつ
    // 試合番号順に重複排除して各スロットの予測チームを確定させる。
    // (確定チームとスロット対応のズレ等で同じ国が複数枠に出るのを防ぐ)
    const claimed = new Set();
    matches.forEach((node) => {
      if (node.home_team) {
        claimed.add(node.home_team);
      }
      if (node.away_team) {
        claimed.add(node.away_team);
      }
    });
    const resolved = new Map();
    [...matches]
      .sort((a, b) => (a.match_no || 0) - (b.match_no || 0))
      .forEach((node) => {
        ["home", "away"].forEach((which) => {
          if (node[`${which}_team`]) {
            return; // 確定済みは予測しない
          }
          const slot = node[which];
          if (!slot) {
            return;
          }
          let row = null;
          if (slot.type === "group" && slot.group && slot.rank) {
            row = (groupRanks.get(slot.group) || [])[slot.rank === "W" ? 0 : 1] || null;
          } else if (slot.type === "third") {
            row = thirdAssign.get(`${node.match_no}.${which}`) || null;
          }
          if (row && row.team && !claimed.has(row.team)) {
            claimed.add(row.team);
            resolved.set(`${node.match_no}.${which}`, row);
          }
        });
      });

    return { resolved };
  }

  // スロット(候補グループを持つ) と 3位通過チーム の二部マッチング (Kuhn法)
  function assignThirds(slots, thirds) {
    const candidates = thirds.map((row) => ({
      row,
      letter: String(row.group).split("_")[1] || row.group,
    }));
    const slotMatch = new Array(slots.length).fill(-1);
    const thirdMatch = new Array(candidates.length).fill(-1);

    function augment(slotIndex, seen) {
      for (let ti = 0; ti < candidates.length; ti += 1) {
        if (seen[ti] || !slots[slotIndex].groups.includes(candidates[ti].letter)) {
          continue;
        }
        seen[ti] = true;
        if (thirdMatch[ti] === -1 || augment(thirdMatch[ti], seen)) {
          slotMatch[slotIndex] = ti;
          thirdMatch[ti] = slotIndex;
          return true;
        }
      }
      return false;
    }

    for (let si = 0; si < slots.length; si += 1) {
      augment(si, new Array(candidates.length).fill(false));
    }
    const map = new Map();
    slots.forEach((slot, si) => {
      if (slotMatch[si] !== -1) {
        map.set(slot.key, candidates[slotMatch[si]].row);
      }
    });
    return map;
  }

  // node の home/away スロットに対応する予測チーム行を返す (重複排除済み・R32 のみ)
  function projectionFor(node, which) {
    if (!proj) {
      return null;
    }
    return proj.resolved.get(`${node.match_no}.${which}`) || null;
  }

  function render(data) {
    const matches = (data && data.matches) || [];
    if (matches.length === 0) {
      container.replaceChildren(
        app.emptyState(
          "トーナメント表はまだありません",
          "グループステージの終了後、決勝トーナメントの組み合わせがここに表示されます。",
        ),
      );
      return;
    }
    nodeByNo = new Map(matches.map((node) => [node.match_no, node]));
    proj = buildProjection(scheduleData, matches);

    renderRoundNav();

    const tree = app.element("div", "bracket-tree");
    tree.append(
      buildHalf(LEFT_COLS, "left"),
      buildCenter(),
      buildHalf(RIGHT_COLS, "right"),
    );

    container.replaceChildren(tree);

    // 初期スクロール位置: PCは中央(決勝)を、スマホはまず左端(ラウンド32)を見せる
    requestAnimationFrame(() => {
      if (window.matchMedia("(min-width: 761px)").matches) {
        container.scrollLeft = Math.max(
          0,
          (container.scrollWidth - container.clientWidth) / 2,
        );
      } else {
        container.scrollLeft = 0;
      }
    });
  }

  function setActiveTab(activeButton) {
    roundTabButtons.forEach((button) => {
      button.classList.toggle("is-active", button === activeButton);
    });
  }

  function buildHalf(columns, side) {
    const half = app.element("div", `bracket-half side-${side}`);
    columns.forEach((column) => {
      const col = app.element("div", "bk-col");
      col.id = `bk-${side}-${column.stage}`;
      col.classList.add(
        column.stage === "SEMI_FINALS" ? "bk-col--semi" : "bk-col--pair",
      );
      col.append(buildColHead(column));

      const body = app.element("div", "bk-col-body");
      column.nos.forEach((no) => {
        const wrap = app.element("div", "bk-wrap");
        const node = nodeByNo.get(no);
        if (node) {
          wrap.append(buildMatchCell(node));
        }
        body.append(wrap);
      });
      col.append(body);
      half.append(col);
    });
    return half;
  }

  function buildColHead(column) {
    const head = app.element("div", "bk-col-head");
    head.append(app.element("span", "bk-col-title", column.label));
    const range = dateRangeOf(column.nos);
    if (range) {
      head.append(app.element("span", "bk-col-date", range));
    }
    return head;
  }

  function buildCenter() {
    const center = app.element("div", "bracket-center");
    center.id = "bk-center";

    const final = nodeByNo.get(104);
    const champ = championOf(final);
    const trophy = app.element("div", `bk-champion${champ ? " is-set" : ""}`);
    trophy.append(trophyIcon());
    trophy.append(
      app.element("span", "bk-champion-label", champ ? "CHAMPION" : "優勝者"),
    );
    trophy.append(
      app.element("span", "bk-champion-name", champ ? champ.name : "未定"),
    );

    const finalBlock = app.element("div", "bk-final-block");
    finalBlock.append(app.element("span", "bk-final-tag", "決勝 / FINAL"));
    if (final) {
      finalBlock.append(buildMatchCell(final));
    }

    center.append(champ ? trophy : app.element("div", "bk-champion"), finalBlock);

    const third = nodeByNo.get(103);
    if (third) {
      const wrap = app.element("div", "bk-third");
      wrap.append(app.element("span", "bk-third-label", "3位決定戦"));
      wrap.append(buildMatchCell(third));
      center.append(wrap);
    }
    return center;
  }

  function championOf(final) {
    if (!final || final.status !== "FINISHED") {
      return null;
    }
    const side = winnerSide(final);
    if (!side) {
      return null;
    }
    return sideInfo(final, side);
  }

  function renderRoundNav() {
    if (!roundsNav) {
      return;
    }
    const buttons = ROUND_TABS.map((tab, index) => {
      const btn = app.element(
        "button",
        `bracket-round-tab${index === 0 ? " is-active" : ""}`,
        tab.label,
      );
      btn.type = "button";
      btn.addEventListener("click", () => {
        setActiveTab(btn);
        const target = document.getElementById(tab.target);
        if (target) {
          target.scrollIntoView({
            behavior: "smooth",
            block: "nearest",
            inline: "center",
          });
        }
      });
      return btn;
    });
    roundTabButtons = buttons;
    roundsNav.replaceChildren(...buttons);
  }

  function dateRangeOf(nos) {
    const dates = nos
      .map((no) => nodeByNo.get(no))
      .filter(Boolean)
      .map((node) => node.date_jst)
      .filter(Boolean)
      .sort();
    if (dates.length === 0) {
      return "";
    }
    const first = app.formatDay(dates[0]);
    const last = app.formatDay(dates[dates.length - 1]);
    return first === last ? first : `${first} – ${last}`;
  }

  // home/away の表示情報。確定チーム > 順位からの暫定予測 > スロット表記 の優先順。
  function sideInfo(node, which) {
    const teamKey = node[`${which}_team`];
    const teamJa = node[`${which}_ja`];
    const slot = node[which] || {};
    if (teamKey) {
      return {
        determined: true,
        team: teamKey,
        name: teamJa || teamKey,
        flag: app.flagEmoji(teamKey),
      };
    }
    const projected = projectionFor(node, which);
    if (projected && projected.team) {
      return {
        determined: false,
        provisional: true,
        team: projected.team,
        name: projected.team_ja || projected.team,
        flag: app.flagEmoji(projected.team),
        pos: positionLabel(slot, projected),
      };
    }
    return { determined: false, name: slot.label || "未定", flag: "" };
  }

  // 予測チームが「何組の何位か」のラベル (例: E組1位 / C組3位)
  function positionLabel(slot, projected) {
    if (slot.type === "group" && slot.group) {
      return `${slot.group}組${slot.rank === "W" ? "1" : "2"}位`;
    }
    if (slot.type === "third") {
      const letter = String(projected.group || "").split("_")[1] || projected.group;
      return letter ? `${letter}組3位` : "3位";
    }
    return "";
  }

  function winnerSide(node) {
    if (node.status !== "FINISHED") {
      return null;
    }
    const score = node.score || {};
    if (!Number.isInteger(score.home) || !Number.isInteger(score.away)) {
      return null;
    }
    if (score.home !== score.away) {
      return score.home > score.away ? "home" : "away";
    }
    if (
      Number.isInteger(score.penalties_home) &&
      Number.isInteger(score.penalties_away) &&
      score.penalties_home !== score.penalties_away
    ) {
      return score.penalties_home > score.penalties_away ? "home" : "away";
    }
    return null;
  }

  function scoreFor(node, which) {
    if (node.status !== "FINISHED" && !LIVE_STATUSES.has(node.status)) {
      return "";
    }
    const value = node.score ? node.score[which] : null;
    return Number.isInteger(value) ? String(value) : "";
  }

  function buildSide(node, which, winner) {
    const info = sideInfo(node, which);
    const classes = ["bracket-side"];
    if (winner === which) {
      classes.push("is-winner");
    }
    if (info.provisional) {
      classes.push("is-proj");
    } else if (!info.determined) {
      classes.push("is-slot");
    }
    const row = app.element("div", classes.join(" "));
    const flag = app.element("span", "bracket-flag", info.flag || "•");
    flag.setAttribute("aria-hidden", "true");

    const text = app.element("div", "bracket-side-text");
    text.append(app.element("span", "bracket-team", info.name));
    if (info.provisional) {
      const meta = app.element("div", "bracket-proj-meta");
      if (info.pos) {
        meta.append(app.element("span", "bracket-proj-pos", info.pos));
      }
      meta.append(app.element("span", "bracket-proj-tag", "予測"));
      text.append(meta);
    }
    row.append(flag, text);

    const score = scoreFor(node, which);
    if (score !== "") {
      row.append(app.element("span", "bracket-score", score));
    }
    return row;
  }

  function statusPill(node) {
    if (LIVE_STATUSES.has(node.status)) {
      return app.pill("LIVE", "live");
    }
    if (node.status === "FINISHED") {
      return app.pill("終了", "finished");
    }
    return null;
  }

  function buildMatchCell(node) {
    const isLink = Boolean(node.fd_id);
    const cell = app.element(isLink ? "a" : "div", "bracket-match glass-card");
    if (node.is_japan) {
      cell.classList.add("is-japan");
    }
    if (LIVE_STATUSES.has(node.status)) {
      cell.classList.add("is-live");
    }
    if (node.status === "FINISHED") {
      cell.classList.add("is-finished");
    }
    if (isLink) {
      cell.href = `match.html?id=${encodeURIComponent(node.fd_id)}`;
    }

    const head = app.element("div", "bracket-match-head");
    head.append(app.element("span", "bracket-no", `M${node.match_no}`));
    const when = node.kickoff_jst
      ? app.formatFullKickoff(node.kickoff_jst)
      : app.formatDay(node.date_jst);
    head.append(app.element("time", "bracket-when", when));
    const pill = statusPill(node);
    if (pill) {
      head.append(pill);
    }

    const winner = winnerSide(node);
    const sides = app.element("div", "bracket-sides");
    sides.append(buildSide(node, "home", winner), buildSide(node, "away", winner));

    const venue = app.element("div", "bracket-venue");
    venue.append(
      venueIcon(),
      app.element("span", "bracket-venue-name", node.venue || "会場未定"),
      app.element("span", "bracket-venue-city", node.city_ja || node.city || ""),
    );

    cell.append(head, sides);
    const probability = buildWinBar(node);
    if (probability) {
      cell.append(probability);
    }
    cell.append(venue);
    if (node.is_japan) {
      cell.append(app.pill("JAPAN MATCH", "japan"));
    }
    return cell;
  }

  // FIFAランク差からの勝率バー (未確定の試合のみ。両者のランクが必要)
  function buildWinBar(node) {
    if (node.status === "FINISHED") {
      return null;
    }
    const home = sideInfo(node, "home");
    const away = sideInfo(node, "away");
    if (!home.team || !away.team) {
      return null;
    }
    const prob = app.winProbability(ranks[home.team], ranks[away.team]);
    if (!prob) {
      return null;
    }
    // どの国が・何%で・どれくらい勝ちやすいかを国名つきで明示する:
    //   ・コールアウト「予想 🇧🇷 ブラジル 62% やや有利」で有利な国を名指し
    //   ・バーは有利側=緑/格下=控えめ (ホーム/アウェイ位置に依存しない)
    //   ・バー下に両国の国旗つき % を併記 (格下側は控えめ)
    const homeFav = prob.home >= prob.away;
    const even = prob.home === prob.away;
    const fav = homeFav ? home : away;
    const favPct = Math.max(prob.home, prob.away);
    const strength = even ? "互角" : strengthLabel(favPct);

    const wrap = app.element("div", "bracket-prob");

    // 予想コールアウト (どの国が有利か)
    const callout = app.element("div", "bracket-prob-callout");
    callout.append(app.element("span", "bracket-prob-lead", "予想"));
    if (even) {
      callout.append(
        app.element("span", "bracket-prob-fav-tag", `互角 ${prob.home}%-${prob.away}%`),
      );
    } else {
      const favFlag = app.element("span", "bracket-prob-fav-flag", fav.flag || "");
      favFlag.setAttribute("aria-hidden", "true");
      callout.append(
        favFlag,
        app.element("span", "bracket-prob-fav-name", fav.name),
        app.element("span", "bracket-prob-fav-pct", `${favPct}%`),
        app.element("span", "bracket-prob-fav-tag", strength),
      );
    }

    // バー (有利側=緑)
    const bar = app.element("div", "bracket-prob-bar");
    const homeFill = app.element(
      "span",
      `bracket-prob-fill ${even ? "" : homeFav ? "is-fav" : "is-under"}`,
    );
    homeFill.style.width = `${prob.home}%`;
    const awayFill = app.element(
      "span",
      `bracket-prob-fill ${even ? "" : homeFav ? "is-under" : "is-fav"}`,
    );
    awayFill.style.width = `${prob.away}%`;
    bar.append(homeFill, awayFill);

    // 両国の国旗つき % (左=home / 右=away、上のチーム行と並びを合わせる)
    const ends = app.element("div", "bracket-prob-ends");
    ends.append(
      buildProbEnd(home, prob.home, !even && homeFav),
      buildProbEnd(away, prob.away, !even && !homeFav),
    );

    wrap.append(callout, bar, ends);
    return wrap;
  }

  function buildProbEnd(info, pct, isFav) {
    const span = app.element(
      "span",
      `bracket-prob-end ${isFav ? "is-fav" : "is-under"}`,
    );
    const flag = app.element("span", "bracket-prob-end-flag", info.flag || "");
    flag.setAttribute("aria-hidden", "true");
    span.append(
      flag,
      app.element("span", "bracket-prob-end-pct", `${isFav ? "▲" : ""}${pct}%`),
    );
    return span;
  }

  // 勝率(有利側の%)から優勢度の言葉を返す。50%付近=互角、差が開くほど強い表現に。
  function strengthLabel(favPct) {
    if (favPct < 58) return "互角";
    if (favPct < 68) return "やや有利";
    if (favPct < 80) return "有利";
    return "大本命";
  }

  function venueIcon() {
    const span = app.element("span", "bracket-venue-icon");
    span.setAttribute("aria-hidden", "true");
    span.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>';
    return span;
  }

  function trophyIcon() {
    const span = app.element("span", "bk-trophy");
    span.setAttribute("aria-hidden", "true");
    span.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 4h12v4a6 6 0 0 1-12 0z"/><path d="M6 6H4a2 2 0 0 0 2 2M18 6h2a2 2 0 0 1-2 2"/><path d="M9 18h6M10 14v4M14 14v4M8 21h8"/></svg>';
    return span;
  }
});
