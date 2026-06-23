document.addEventListener("DOMContentLoaded", async () => {
  "use strict";

  const app = window.SiteApp;
  const GROUP_F = "GROUP_F";
  const JAPAN = "Japan";
  const POSITIONS = [
    ["GK", "ゴールキーパー"],
    ["DF", "ディフェンダー"],
    ["MF", "ミッドフィールダー"],
    ["FW", "フォワード"],
  ];

  let schedule = [];
  try {
    schedule = await app.fetchJson("data/schedule.json");
    renderJapanKnockout(schedule);
    renderNextJapan(schedule);
    renderGroupF(schedule);
    renderGroupFStandings(schedule);
  } catch (error) {
    app.logDataError(error);
    app.showLoadError(document.querySelector("#next-japan"));
    app.showLoadError(document.querySelector("#japan-matches"));
    app.showLoadError(document.querySelector("#group-f-standings"));
    document.querySelector("#group-f-others")?.setAttribute("aria-busy", "false");
  }

  let teams = [];
  try {
    teams = await app.fetchJson("data/teams.json");
    renderHeroChips(teams);
    renderSquad(teams);
  } catch (error) {
    app.logDataError(error);
    app.showLoadError(document.querySelector("#japan-squad"));
  }

  try {
    const opponentsData = await app.fetchJson("data/japan_opponents.json");
    renderOpponents(opponentsData, teams, schedule);
  } catch (error) {
    app.logDataError(error);
    app.showLoadError(document.querySelector("#opponents"));
  }

  /* --- 0. 決勝トーナメント進出ハイライト (日本がKOに進んだ時だけ表示) ------ */

  const KO_ADVANCE = {
    LAST_32: "ベスト16",
    LAST_16: "ベスト8",
    QUARTER_FINALS: "ベスト4",
    SEMI_FINALS: "決勝",
  };

  function japanKnockoutMatches(matches) {
    return matches
      .filter((match) => match.is_japan && match.stage !== "GROUP_STAGE")
      .sort(
        (a, b) =>
          new Date(a.kickoff_jst).getTime() - new Date(b.kickoff_jst).getTime(),
      );
  }

  function japanWon(match) {
    if (match.status !== "FINISHED") {
      return null;
    }
    const score = match.score || {};
    const japanHome = match.home === JAPAN;
    let jp = japanHome ? score.home : score.away;
    let opp = japanHome ? score.away : score.home;
    if (!Number.isInteger(jp) || !Number.isInteger(opp)) {
      return null;
    }
    if (jp !== opp) {
      return jp > opp;
    }
    const jpPk = japanHome ? score.penalties_home : score.penalties_away;
    const oppPk = japanHome ? score.penalties_away : score.penalties_home;
    if (Number.isInteger(jpPk) && Number.isInteger(oppPk) && jpPk !== oppPk) {
      return jpPk > oppPk;
    }
    return null;
  }

  function knockoutStatusText(last) {
    const won = japanWon(last);
    if (last.status !== "FINISHED" || won === null) {
      return `${last.stage_ja || "決勝トーナメント"} 進出中 🔥`;
    }
    if (won) {
      if (last.stage === "FINAL") return "🏆 世界一！！！";
      if (last.stage === "THIRD_PLACE") return "🥉 堂々の3位！";
      if (last.stage === "SEMI_FINALS") return "✨ 決勝進出！";
      return `✨ ${KO_ADVANCE[last.stage] || ""}進出！`;
    }
    if (last.stage === "FINAL") return "🥈 準優勝";
    if (last.stage === "THIRD_PLACE") return "4位";
    return `${last.stage_ja || ""}で敗退`;
  }

  function renderJapanKnockout(matches) {
    const section = document.querySelector("#japan-knockout-section");
    const container = document.querySelector("#japan-knockout");
    if (!section || !container) {
      return;
    }
    const knockout = japanKnockoutMatches(matches);
    if (knockout.length === 0) {
      section.hidden = true;
      return;
    }
    section.hidden = false;

    const banner = app.element("div", "jp-ko-banner glass-card");
    banner.append(app.element("p", "jp-ko-kicker", "🎌 KNOCKOUT STAGE"));
    banner.append(
      app.element("p", "jp-ko-status", knockoutStatusText(knockout[knockout.length - 1])),
    );

    const path = app.element("div", "jp-ko-path");
    knockout.forEach((match) => {
      const item = app.element("div", "jp-ko-step");
      item.append(app.element("span", "jp-ko-round", match.stage_ja || "決勝T"));
      item.append(createMiniMatchRow(match));
      path.append(item);
    });

    container.replaceChildren(banner, path);
  }

  /* --- 1. ヒーロー: W杯戦績チップ (teams.json から動的) --------------------- */

  function chip(text, extraClass) {
    return app.element(
      "span",
      extraClass ? `japan-chip ${extraClass}` : "japan-chip",
      text,
    );
  }

  function renderHeroChips(teamList) {
    const container = document.querySelector("#japan-hero-chips");
    const japan = (teamList || []).find((team) => team.name === JAPAN);
    if (!container || !japan) {
      return;
    }
    const chips = [];
    const history = japan.history || {};
    if (Number.isInteger(history.appearances) && history.appearances > 0) {
      chips.push(chip(`W杯出場${history.appearances}回目`));
    }
    if (history.best) {
      chips.push(chip(`過去最高 ${history.best}`));
    }
    if (history.last && history.last.year) {
      chips.push(
        chip(`前回${history.last.year} ${history.last.result || ""}`.trim()),
      );
    }
    if (Number.isInteger(japan.rank)) {
      chips.push(chip(`FIFAランク ${japan.rank}位`, "is-rank"));
    }
    container.replaceChildren(...chips);
  }

  /* --- 2. 次の日本戦カウントダウン (index.js のロジック流用) ------------------- */

  function findNextJapanMatch(matches) {
    return matches
      .filter((match) => match.is_japan && app.isUpcoming(match))
      .sort(
        (left, right) =>
          new Date(left.kickoff_jst) - new Date(right.kickoff_jst),
      )[0];
  }

  function heroTeam(name, displayName) {
    const node = app.element("div", "hmc-team");
    const flag = app.element("span", "hmc-team-flag", app.flagEmoji(name));
    flag.setAttribute("aria-hidden", "true");
    node.append(flag, app.element("span", "hmc-team-name", displayName || name));
    return node;
  }

  function renderNextJapan(matches) {
    const container = document.querySelector("#next-japan");
    const nextMatch = findNextJapanMatch(matches);
    container.setAttribute("aria-busy", "false");

    if (!nextMatch) {
      container.replaceChildren(
        app.emptyState(
          "次の日本戦は未定です",
          "日程が決まり次第、ここに表示されます。",
        ),
      );
      return;
    }

    const card = app.element("article", "hero-match-card glass-card");

    const info = app.element("div", "hmc-info");
    const kickoff = app.element("p", "hmc-kickoff");
    kickoff.append(
      app.element(
        "strong",
        "",
        `${app.formatFullKickoff(nextMatch.kickoff_jst)}`,
      ),
      "キックオフ (日本時間)",
    );
    info.append(
      app.pill("JAPAN MATCH", "japan"),
      app.element("p", "hmc-stage", nextMatch.stage_ja || "ステージ未定"),
      kickoff,
    );
    const detailLink = app.element("a", "hmc-detail-link", "試合詳細を見る ▸");
    detailLink.href = `match.html?id=${encodeURIComponent(nextMatch.id)}`;
    info.append(detailLink);

    const versus = app.element("div", "hmc-versus");
    versus.append(
      heroTeam(nextMatch.home, nextMatch.home_ja),
      app.element("span", "hmc-vs", "VS"),
      heroTeam(nextMatch.away, nextMatch.away_ja),
    );

    const countdown = app.element("div", "hmc-countdown");
    countdown.append(app.element("p", "hmc-countdown-label", "KICKOFF IN"));
    const clock = app.element("div", "countdown-clock");
    const units = [
      ["days", "日"],
      ["hours", "時間"],
      ["minutes", "分"],
      ["seconds", "秒"],
    ];
    const valueNodes = {};
    units.forEach(([key, label]) => {
      const unit = app.element("div", "countdown-unit");
      const value = app.element("span", "countdown-value", "00");
      valueNodes[key] = value;
      unit.append(value, app.element("span", "countdown-name", label));
      clock.append(unit);
    });
    countdown.append(clock);

    card.append(info, versus, countdown);
    container.replaceChildren(card);

    const update = () => {
      const remaining = new Date(nextMatch.kickoff_jst).getTime() - Date.now();
      if (remaining <= 0) {
        countdown.replaceChildren(
          app.element("p", "hmc-countdown-label", "まもなくキックオフ！"),
        );
        window.clearInterval(timerId);
        return;
      }
      const totalSeconds = Math.floor(remaining / 1000);
      valueNodes.days.textContent = String(
        Math.floor(totalSeconds / 86400),
      ).padStart(2, "0");
      valueNodes.hours.textContent = String(
        Math.floor((totalSeconds % 86400) / 3600),
      ).padStart(2, "0");
      valueNodes.minutes.textContent = String(
        Math.floor((totalSeconds % 3600) / 60),
      ).padStart(2, "0");
      valueNodes.seconds.textContent = String(totalSeconds % 60).padStart(
        2,
        "0",
      );
    };
    update();
    const timerId = window.setInterval(update, 1000);
  }

  /* --- 3. グループFの戦い --------------------------------------------------- */

  function groupFMatches(matches) {
    return matches
      .filter((match) => match.group === GROUP_F)
      .sort(
        (left, right) =>
          new Date(left.kickoff_jst) - new Date(right.kickoff_jst),
      );
  }

  function renderGroupF(matches) {
    const japanContainer = document.querySelector("#japan-matches");
    const othersContainer = document.querySelector("#group-f-others");
    japanContainer.setAttribute("aria-busy", "false");
    othersContainer.setAttribute("aria-busy", "false");

    const groupF = groupFMatches(matches);
    const japanMatches = groupF.filter((match) => match.is_japan);
    const others = groupF.filter((match) => !match.is_japan);

    if (japanMatches.length === 0) {
      japanContainer.replaceChildren(
        app.emptyState(
          "日本戦の日程がまだありません",
          "日程が決まり次第、ここに表示されます。",
        ),
      );
    } else {
      japanContainer.replaceChildren(
        ...japanMatches.map((match) => {
          // 試合カードは app.createMatchCard を流用し、時刻を日付込みに差し替え
          const card = app.createMatchCard(match);
          const time = card.querySelector(".match-time");
          if (time) {
            time.textContent = app.formatFullKickoff(match.kickoff_jst);
          }
          return card;
        }),
      );
    }

    if (others.length === 0) {
      othersContainer.replaceChildren(
        app.emptyState("グループFのその他の試合はありません"),
      );
      return;
    }
    othersContainer.replaceChildren(...others.map(createMiniMatchRow));
  }

  function miniTeam(name, displayName, alignRight) {
    const node = app.element(
      "span",
      alignRight ? "jp-mini-team is-right" : "jp-mini-team",
    );
    const flag = app.element("span", "jp-mini-flag", app.flagEmoji(name));
    flag.setAttribute("aria-hidden", "true");
    const label = app.element("span", "jp-mini-name", displayName || name);
    if (alignRight) {
      node.append(label, flag);
    } else {
      node.append(flag, label);
    }
    return node;
  }

  function createMiniMatchRow(match) {
    const row = app.element("a", "jp-mini-match glass-card");
    row.href = `match.html?id=${encodeURIComponent(match.id)}`;

    const date = app.element(
      "time",
      "jp-mini-date",
      app.formatFullKickoff(match.kickoff_jst),
    );

    const center = app.element("span", "jp-mini-center");
    center.append(
      miniTeam(match.home, match.home_ja),
      app.element("span", "jp-mini-score", scoreLabel(match)),
      miniTeam(match.away, match.away_ja, true),
    );

    row.append(date, center, app.element("span", "jp-mini-status", app.statusText(match)));
    return row;
  }

  function scoreLabel(match) {
    if (
      match.status === "FINISHED" &&
      Number.isInteger(match.score?.home) &&
      Number.isInteger(match.score?.away)
    ) {
      return `${match.score.home} - ${match.score.away}`;
    }
    return "vs";
  }

  /* --- 4. 対戦相手を知る ------------------------------------------------------ */

  function renderOpponents(opponentsData, teamList, matches) {
    const container = document.querySelector("#opponents");
    container.setAttribute("aria-busy", "false");

    const opponents = opponentsData?.opponents || {};
    const names = Object.keys(opponents);
    if (names.length === 0) {
      container.replaceChildren(
        app.emptyState(
          "対戦相手データを準備中です",
          "公開され次第、ここに表示されます。",
        ),
      );
      return;
    }

    const rankByName = new Map(
      (teamList || []).map((team) => [team.name, team.rank]),
    );
    const matchById = new Map((matches || []).map((match) => [match.id, match]));

    // 対戦順 (試合日時順) に並べる
    const sorted = names.slice().sort((left, right) => {
      const leftMatch = matchById.get(opponents[left].match_id);
      const rightMatch = matchById.get(opponents[right].match_id);
      if (!leftMatch || !rightMatch) {
        return 0;
      }
      return new Date(leftMatch.kickoff_jst) - new Date(rightMatch.kickoff_jst);
    });

    container.replaceChildren(
      ...sorted.map((name) =>
        createOpponentCard(name, opponents[name], rankByName, matchById),
      ),
    );
  }

  function createOpponentCard(name, opponent, rankByName, matchById) {
    const card = app.element("article", "opponent-card glass-card");

    const head = app.element("div", "opponent-head");
    const flag = app.element("span", "team-flag-lg", app.flagEmoji(name));
    flag.setAttribute("aria-hidden", "true");
    const heading = app.element("div", "team-heading");
    const title = app.element("h3", "team-title", opponent.name_ja || name);
    title.append(app.element("span", "team-english", name));
    heading.append(title);
    head.append(flag, heading);
    const rank = rankByName.get(name);
    head.append(
      app.element(
        "span",
        "rank-badge",
        Number.isInteger(rank) ? `FIFA ${rank}位` : "FIFAランク 準備中",
      ),
    );
    card.append(head);

    if (opponent.blurb) {
      card.append(app.element("p", "opponent-blurb", opponent.blurb));
    }

    if (Array.isArray(opponent.key_players) && opponent.key_players.length > 0) {
      card.append(app.element("p", "opponent-label", "注目選手"));
      const list = app.element("ul", "opponent-players");
      opponent.key_players.forEach((player) => {
        list.append(app.element("li", "", player));
      });
      card.append(list);
    }

    if (opponent.vs_japan) {
      card.append(app.element("p", "opponent-label", "日本との対戦"));
      card.append(app.element("p", "opponent-vs", opponent.vs_japan));
    }

    const match = matchById.get(opponent.match_id);
    if (match) {
      const link = app.element(
        "a",
        "neon-btn neon-btn-secondary opponent-cta",
        `${app.formatFullKickoff(match.kickoff_jst)} の試合詳細 ▸`,
      );
      link.href = `match.html?id=${encodeURIComponent(match.id)}`;
      card.append(link);
    }
    return card;
  }

  /* --- 5. グループF順位表 (standings.js の computeStandings を再利用) ---------- */

  function signedGd(value) {
    return value > 0 ? `+${value}` : String(value);
  }

  function renderGroupFStandings(matches) {
    const container = document.querySelector("#group-f-standings");
    container.setAttribute("aria-busy", "false");

    const standings = window.SiteStandings.computeStandings(matches);
    const groupF = standings.find((entry) => entry.group === GROUP_F);
    if (!groupF) {
      container.replaceChildren(
        app.emptyState(
          "グループFのデータがありません",
          "時間をおいてからページを再読み込みしてください。",
        ),
      );
      return;
    }

    const card = app.element("section", "standings-card glass-card is-japan");
    const head = app.element("div", "standings-card-head");
    head.append(
      app.element("h3", "standings-card-title", app.formatGroup(groupF.group)),
      app.pill("JAPAN", "japan"),
    );
    card.append(head);

    const table = app.element("table", "st-table");
    const thead = app.element("thead");
    const headTr = app.element("tr");
    [
      ["#", "st-col-rank"],
      ["国", "st-col-team"],
      ["試", "st-col-num"],
      ["勝", "st-col-num"],
      ["分", "st-col-num"],
      ["負", "st-col-num"],
      ["得失", "st-col-gd"],
      ["勝点", "st-col-pts"],
    ].forEach(([label, className]) => {
      const th = app.element("th", className || "", label);
      th.setAttribute("scope", "col");
      headTr.append(th);
    });
    thead.append(headTr);

    const tbody = app.element("tbody");
    groupF.teams.forEach((row) => {
      const classNames = [];
      if (row.rank <= 2) {
        classNames.push("is-qualify");
      }
      if (row.rank === 3) {
        classNames.push("is-third");
      }
      const tr = app.element("tr", classNames.join(" "));

      const rankCell = app.element("td", "st-rank");
      if (row.rank === 3) {
        rankCell.append(app.element("span", "st-badge-third", "3位"));
      } else {
        rankCell.textContent = String(row.rank);
      }

      const teamCell = app.element("td", "st-team-cell");
      const wrapper = app.element("span", "st-team");
      const flag = app.element("span", "st-flag", app.flagEmoji(row.team));
      flag.setAttribute("aria-hidden", "true");
      wrapper.append(flag, app.element("span", "st-name", row.team_ja));
      if (row.live) {
        wrapper.append(app.element("span", "st-live", "LIVE"));
      }
      teamCell.append(wrapper);

      tr.append(
        rankCell,
        teamCell,
        app.element("td", "", String(row.played)),
        app.element("td", "", String(row.won)),
        app.element("td", "", String(row.drawn)),
        app.element("td", "", String(row.lost)),
        app.element("td", "st-gd", signedGd(row.gd)),
        app.element("td", "st-pts", String(row.points)),
      );
      tbody.append(tr);
    });
    table.append(thead, tbody);
    card.append(table);
    container.replaceChildren(card);
  }

  /* --- 6. メンバー26人 (ポジション別) ----------------------------------------- */

  function createAvatarFallback(player) {
    const fallback = app.element(
      "span",
      "player-avatar-fallback",
      player.number == null ? "−" : String(player.number),
    );
    fallback.setAttribute("aria-hidden", "true");
    return fallback;
  }

  function createAvatar(player) {
    const avatar = app.element("span", "player-avatar jp-player-avatar");
    if (player.photo) {
      const img = document.createElement("img");
      img.className = "player-avatar-img";
      img.src = player.photo;
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.referrerPolicy = "no-referrer";
      img.addEventListener("error", () => {
        avatar.replaceChildren(createAvatarFallback(player));
      });
      avatar.append(img);
    } else {
      avatar.append(createAvatarFallback(player));
    }
    return avatar;
  }

  function createPlayerCard(player) {
    const card = app.element("div", "jp-player-card glass-card");
    card.append(createAvatar(player));
    card.append(
      app.element(
        "span",
        "jp-player-number",
        player.number == null ? "−" : `#${player.number}`,
      ),
    );
    card.append(
      app.element(
        "span",
        "jp-player-name",
        player.name_ja || player.name || "未定",
      ),
    );
    return card;
  }

  function renderSquad(teamList) {
    const container = document.querySelector("#japan-squad");
    container.setAttribute("aria-busy", "false");

    const japan = (teamList || []).find((team) => team.name === JAPAN);
    const squad = japan && Array.isArray(japan.squad) ? japan.squad : [];
    if (squad.length === 0) {
      container.replaceChildren(
        app.emptyState(
          "メンバーデータを準備中です",
          "発表され次第、ここに表示されます。",
        ),
      );
      return;
    }

    const blocks = [];
    POSITIONS.forEach(([position, label]) => {
      const players = squad
        .filter((player) => player.position === position)
        .sort(
          (left, right) =>
            (Number(left.number) || 999) - (Number(right.number) || 999),
        );
      if (players.length === 0) {
        return;
      }
      const block = app.element("div", "jp-squad-block");
      const heading = app.element("h3", "japan-sub-title", `${position}`);
      heading.append(app.element("span", "jp-position-ja", label));
      block.append(heading);
      const grid = app.element("div", "jp-squad-grid");
      grid.append(...players.map(createPlayerCard));
      block.append(grid);
      blocks.push(block);
    });
    container.replaceChildren(...blocks);
  }
});
