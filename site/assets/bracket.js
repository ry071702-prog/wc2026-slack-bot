document.addEventListener("DOMContentLoaded", async () => {
  "use strict";

  const app = window.SiteApp;
  const container = document.querySelector("#bracket");
  const roundsNav = document.querySelector("#bracket-rounds");

  const LIVE_STATUSES = new Set(["IN_PLAY", "PAUSED"]);
  // ラウンド32〜決勝を列として描く。3位決定戦は決勝列に併記する。
  const COLUMNS = [
    { stage: "LAST_32", label: "ラウンド32", short: "R32" },
    { stage: "LAST_16", label: "ラウンド16", short: "R16" },
    { stage: "QUARTER_FINALS", label: "準々決勝", short: "QF" },
    { stage: "SEMI_FINALS", label: "準決勝", short: "SF" },
    { stage: "FINAL", label: "決勝", short: "決勝" },
  ];

  let bracket = null;
  try {
    bracket = await app.fetchJson("data/bracket.json");
    container.setAttribute("aria-busy", "false");
    render(bracket);
  } catch (error) {
    app.logDataError(error);
    app.showLoadError(container);
  }

  function byStage(matches, stage) {
    return matches
      .filter((match) => match.stage === stage)
      .sort((a, b) => (a.match_no || 0) - (b.match_no || 0));
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

    renderRoundNav();

    const track = app.element("div", "bracket-track");
    COLUMNS.forEach((column) => {
      const col = app.element("div", "bracket-col");
      col.id = `round-${column.stage}`;
      col.append(buildColumnHeader(column, matches));

      const body = app.element("div", "bracket-col-body");
      byStage(matches, column.stage).forEach((node) => {
        body.append(buildMatchCell(node));
      });

      // 3位決定戦は決勝の下に小さく併記する
      if (column.stage === "FINAL") {
        const third = byStage(matches, "THIRD_PLACE")[0];
        if (third) {
          body.append(buildThirdPlace(third));
        }
      }
      col.append(body);
      track.append(col);
    });

    container.replaceChildren(track);
  }

  function renderRoundNav() {
    if (!roundsNav) {
      return;
    }
    const buttons = COLUMNS.map((column) => {
      const btn = app.element("button", "bracket-round-tab", column.label);
      btn.type = "button";
      btn.dataset.target = `round-${column.stage}`;
      btn.addEventListener("click", () => {
        const target = document.getElementById(btn.dataset.target);
        if (target) {
          target.scrollIntoView({
            behavior: "smooth",
            block: "nearest",
            inline: "start",
          });
        }
      });
      return btn;
    });
    roundsNav.replaceChildren(...buttons);
  }

  function buildColumnHeader(column, matches) {
    const header = app.element("div", "bracket-col-head");
    header.append(app.element("span", "bracket-col-title", column.label));
    const range = dateRange(byStage(matches, column.stage));
    if (range) {
      header.append(app.element("span", "bracket-col-date", range));
    }
    return header;
  }

  function dateRange(nodes) {
    const dates = nodes
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
      return { determined: true, name: teamJa || teamKey, flag: app.flagEmoji(teamKey), type: "team" };
    }
    return { determined: false, name: slot.label || "未定", flag: "", type: slot.type || "tbd" };
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

  function buildThirdPlace(node) {
    const wrap = app.element("div", "bracket-third");
    wrap.append(app.element("span", "bracket-third-label", "3位決定戦"));
    wrap.append(buildMatchCell(node));
    return wrap;
  }

  function venueIcon() {
    const span = app.element("span", "bracket-venue-icon");
    span.setAttribute("aria-hidden", "true");
    span.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>';
    return span;
  }
});
