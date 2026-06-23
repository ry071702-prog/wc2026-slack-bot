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
  // ナビ用 (左列 + 中央決勝)
  const ROUND_TABS = [
    { label: "ラウンド32", target: "bk-left-LAST_32" },
    { label: "ラウンド16", target: "bk-left-LAST_16" },
    { label: "準々決勝", target: "bk-left-QUARTER_FINALS" },
    { label: "準決勝", target: "bk-left-SEMI_FINALS" },
    { label: "決勝", target: "bk-center" },
  ];

  let nodeByNo = new Map();

  try {
    const bracket = await app.fetchJson("data/bracket.json");
    container.setAttribute("aria-busy", "false");
    render(bracket);
  } catch (error) {
    app.logDataError(error);
    app.showLoadError(container);
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

    renderRoundNav();

    const tree = app.element("div", "bracket-tree");
    tree.append(
      buildHalf(LEFT_COLS, "left"),
      buildCenter(),
      buildHalf(RIGHT_COLS, "right"),
    );

    container.replaceChildren(tree);
    // 初期表示は中央(決勝)が見えるようスクロール位置を寄せる
    requestAnimationFrame(() => {
      container.scrollLeft = Math.max(
        0,
        (container.scrollWidth - container.clientWidth) / 2,
      );
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
    const buttons = ROUND_TABS.map((tab) => {
      const btn = app.element("button", "bracket-round-tab", tab.label);
      btn.type = "button";
      btn.addEventListener("click", () => {
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

  // home/away の表示情報。確定チームがあれば国旗+日本語名、無ければスロット表記。
  function sideInfo(node, which) {
    const teamKey = node[`${which}_team`];
    const teamJa = node[`${which}_ja`];
    const slot = node[which] || {};
    if (teamKey) {
      return { determined: true, name: teamJa || teamKey, flag: app.flagEmoji(teamKey) };
    }
    return { determined: false, name: slot.label || "未定", flag: "" };
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
    const row = app.element(
      "div",
      `bracket-side${winner === which ? " is-winner" : ""}${info.determined ? "" : " is-slot"}`,
    );
    const flag = app.element("span", "bracket-flag", info.flag || "•");
    flag.setAttribute("aria-hidden", "true");
    row.append(flag, app.element("span", "bracket-team", info.name));
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

    cell.append(head, sides, venue);
    if (node.is_japan) {
      cell.append(app.pill("JAPAN MATCH", "japan"));
    }
    return cell;
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
