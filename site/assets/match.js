document.addEventListener("DOMContentLoaded", async () => {
  "use strict";

  const app = window.SiteApp;
  const container = document.querySelector("#match-detail");
  const liveStatuses = new Set(["IN_PLAY", "PAUSED"]);
  const matchId = new URLSearchParams(window.location.search).get("id");

  if (!matchId) {
    renderNotFound();
    return;
  }

  try {
    const [schedule, highlights, facts, stats] = await Promise.all([
      app.fetchJson("data/schedule.json"),
      app.fetchJson("data/highlights.json", { optional: true }),
      app.fetchJson("data/match_facts.json", { optional: true }),
      app.fetchJson("data/match_stats.json", { optional: true }),
    ]);
    const match = schedule.find((item) => String(item.id) === matchId);
    if (!match) {
      renderNotFound();
      return;
    }
    render(match, highlights || {}, facts || {}, stats || {});
  } catch (error) {
    app.logDataError(error);
    app.showLoadError(container);
  }

  function renderNotFound() {
    container.setAttribute("aria-busy", "false");
    container.replaceChildren(
      app.emptyState(
        "試合が見つかりません",
        "URLが正しいか確認するか、全日程から試合を選び直してください。",
      ),
    );
  }

  function render(match, highlights, facts, stats) {
    container.setAttribute("aria-busy", "false");
    const homeName = match.home_ja || match.home;
    const awayName = match.away_ja || match.away;
    document.title = `${homeName} vs ${awayName} | WORLD CUP 2026`;

    const sections = [scoreboard(match)];

    const highlightSection = buildHighlightSection(match, highlights);
    if (highlightSection) {
      sections.push(highlightSection);
    }

    const goalsSection = buildGoalsSection(match, facts);
    if (goalsSection) {
      sections.push(goalsSection);
    }

    const statsSection = buildStatsSection(match, stats);
    if (statsSection) {
      sections.push(statsSection);
    }

    container.replaceChildren(...sections);
  }

  // --- スコアボード -----------------------------------------------------

  function statusPill(match) {
    if (liveStatuses.has(match.status)) {
      return app.pill("LIVE", "live");
    }
    if (match.status === "FINISHED") {
      return app.pill("FULL TIME", "finished");
    }
    return app.pill("予定", "next");
  }

  function hasScore(match) {
    return (
      Number.isInteger(match.score?.home) &&
      Number.isInteger(match.score?.away)
    );
  }

  function boardTeam(name, displayName) {
    const node = app.element("div", "board-team");
    const flag = app.element("span", "board-team-flag", app.flagEmoji(name));
    flag.setAttribute("aria-hidden", "true");
    node.append(
      flag,
      app.element("span", "board-team-name", displayName || name),
    );
    return node;
  }

  function scoreboard(match) {
    const classNames = ["match-board", "glass-card"];
    if (match.is_japan) {
      classNames.push("is-japan");
    }
    if (liveStatuses.has(match.status)) {
      classNames.push("is-live");
    }
    const board = app.element("article", classNames.join(" "));

    const top = app.element("div", "board-top");
    top.append(statusPill(match));
    top.append(
      app.element("span", "board-stage", match.stage_ja || "ステージ未定"),
    );
    if (match.is_japan) {
      top.append(app.pill("JAPAN MATCH", "japan"));
    }
    board.append(top);

    const showScore =
      (match.status === "FINISHED" || liveStatuses.has(match.status)) &&
      hasScore(match);
    const center = app.element("div", "board-center");
    center.append(boardTeam(match.home, match.home_ja));
    if (showScore) {
      center.append(
        app.element(
          "span",
          "board-score",
          `${match.score.home} - ${match.score.away}`,
        ),
      );
    } else {
      const kickoff = app.element("span", "board-kickoff");
      kickoff.append(
        app.element(
          "strong",
          "",
          app.formatKickoff(match.kickoff_jst),
        ),
        app.element("span", "", "キックオフ"),
      );
      center.append(kickoff);
    }
    center.append(boardTeam(match.away, match.away_ja));
    board.append(center);

    const meta = app.element("div", "board-meta");
    const detail = app.statusText(match);
    if (detail.includes("PK") || detail.includes("延長")) {
      meta.append(app.element("span", "board-extra", detail));
    }
    meta.append(
      app.element(
        "span",
        "board-datetime",
        `${app.formatFullKickoff(match.kickoff_jst)} (日本時間)`,
      ),
    );
    if (match.venue) {
      const venue = app.element("span", "board-venue");
      const icon = app.element("span", "board-venue-icon", "📍");
      icon.setAttribute("aria-hidden", "true");
      venue.append(icon, app.element("span", "", match.venue));
      meta.append(venue);
    }
    board.append(meta);
    return board;
  }

  // --- ハイライト ---------------------------------------------------------

  function youtubeVideoId(url) {
    try {
      const parsed = new URL(url);
      let id = null;
      if (parsed.hostname === "youtu.be") {
        id = parsed.pathname.slice(1);
      } else if (parsed.pathname.startsWith("/embed/")) {
        id = parsed.pathname.split("/")[2];
      } else {
        id = parsed.searchParams.get("v");
      }
      return id && /^[\w-]{6,}$/.test(id) ? id : null;
    } catch {
      return null;
    }
  }

  function sectionHeading(eyebrow, title) {
    const header = app.element("div", "detail-section-header");
    header.append(
      app.element("p", "detail-eyebrow", eyebrow),
      app.element("h2", "detail-title", title),
    );
    return header;
  }

  function buildHighlightSection(match, highlights) {
    const entry = highlights[String(match.id)];
    const videoId = entry && entry.url ? youtubeVideoId(entry.url) : null;
    if (!videoId && match.status !== "FINISHED") {
      return null;
    }

    const section = app.element("section", "detail-section");
    section.append(sectionHeading("HIGHLIGHTS", "ハイライト"));

    if (videoId) {
      const frameWrap = app.element("div", "video-embed glass-card");
      const iframe = document.createElement("iframe");
      iframe.src = `https://www.youtube-nocookie.com/embed/${videoId}`;
      iframe.title = entry.title || "ハイライト動画";
      iframe.loading = "lazy";
      iframe.setAttribute(
        "allow",
        "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share",
      );
      iframe.setAttribute("allowfullscreen", "");
      iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      frameWrap.append(iframe);
      section.append(frameWrap);
      if (entry.title) {
        section.append(app.element("p", "video-caption", entry.title));
      }
      return section;
    }

    const card = app.element("div", "highlight-search glass-card");
    card.append(
      app.element(
        "p",
        "highlight-search-note",
        "ハイライト動画は準備中です。DAZN Japan のチャンネルから探せます。",
      ),
    );
    const query = `${match.home_ja || match.home} ${match.away_ja || match.away}`;
    const link = app.element(
      "a",
      "neon-btn neon-btn-primary",
      "▶ ハイライトを探す (DAZN Japan)",
    );
    link.href = `https://www.youtube.com/@DAZNJapan/search?query=${encodeURIComponent(query)}`;
    link.target = "_blank";
    link.rel = "noreferrer";
    card.append(link);
    section.append(card);
    return section;
  }

  // --- 得点詳細 -----------------------------------------------------------

  function buildGoalsSection(match, facts) {
    const entry = facts[String(match.id)];
    const goals = Array.isArray(entry?.goals) ? entry.goals : [];
    if (goals.length === 0) {
      return null;
    }

    const section = app.element("section", "detail-section");
    section.append(sectionHeading("GOALS", "得点詳細"));

    const list = app.element("ol", "goal-timeline glass-card");
    goals.forEach((goal) => {
      const side = goal.team === "away" ? "away" : "home";
      const item = app.element("li", `goal-item goal-${side}`);
      const minuteLabel = goal.minute_label || goal.minute;
      const body = app.element("div", "goal-body");
      body.append(
        app.element("span", "goal-minute", `${minuteLabel}'`),
        app.element("span", "goal-player", goal.player || "得点者不明"),
      );
      const team = app.element(
        "span",
        "goal-team",
        side === "home"
          ? match.home_ja || match.home
          : match.away_ja || match.away,
      );
      body.append(team);
      item.append(body);
      list.append(item);
    });
    section.append(list);
    return section;
  }

  // --- スタッツ (ESPN) -----------------------------------------------------

  function isNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function passLabel(side) {
    if (isNumber(side.passes_accurate) && isNumber(side.passes)) {
      return `${side.passes_accurate}/${side.passes}`;
    }
    if (isNumber(side.passes)) {
      return String(side.passes);
    }
    if (isNumber(side.passes_accurate)) {
      return String(side.passes_accurate);
    }
    return null;
  }

  // 比較で優勢な側を強調するため、数値文字列 ("310/421" は先頭の成功数) を取り出す
  function compareValue(text) {
    if (text === null || text === undefined) {
      return null;
    }
    const matched = String(text).match(/-?\d+(\.\d+)?/);
    return matched ? Number(matched[0]) : null;
  }

  function statRow(label, homeText, awayText) {
    const hasHome = homeText !== null && homeText !== undefined;
    const hasAway = awayText !== null && awayText !== undefined;
    if (!hasHome && !hasAway) {
      return null;
    }
    const row = app.element("div", "stat-row");
    const home = app.element(
      "span",
      "stat-value stat-home",
      hasHome ? String(homeText) : "-",
    );
    const away = app.element(
      "span",
      "stat-value stat-away",
      hasAway ? String(awayText) : "-",
    );
    const homeNum = compareValue(homeText);
    const awayNum = compareValue(awayText);
    if (isNumber(homeNum) && isNumber(awayNum) && homeNum !== awayNum) {
      (homeNum > awayNum ? home : away).classList.add("is-more");
    }
    row.append(
      home,
      app.element("span", "stat-label", label),
      away,
    );
    return row;
  }

  function possessionBlock(homeValue, awayValue) {
    const hasHome = isNumber(homeValue);
    const hasAway = isNumber(awayValue);
    const home = hasHome ? homeValue : 100 - awayValue;
    const away = hasAway ? awayValue : 100 - homeValue;
    const total = home + away;
    const homePct = total > 0 ? (home / total) * 100 : 50;
    const awayPct = 100 - homePct;

    const wrap = app.element("div", "stat-possession");
    wrap.append(
      statRow("ボール支配率", `${Math.round(home)}%`, `${Math.round(away)}%`),
    );

    const bar = app.element("div", "poss-bar");
    bar.setAttribute("role", "img");
    bar.setAttribute(
      "aria-label",
      `ボール支配率 ホーム ${Math.round(home)}% アウェイ ${Math.round(away)}%`,
    );
    const fillHome = app.element("span", "poss-fill poss-home");
    fillHome.style.width = `${homePct}%`;
    const fillAway = app.element("span", "poss-fill poss-away");
    fillAway.style.width = `${awayPct}%`;
    bar.append(fillHome, fillAway);
    wrap.append(bar);
    return wrap;
  }

  function buildStatsSection(match, stats) {
    const entry = stats[String(match.id)];
    if (!entry) {
      return null;
    }
    const home = entry.home || {};
    const away = entry.away || {};
    if (Object.keys(home).length === 0 && Object.keys(away).length === 0) {
      return null;
    }

    const section = app.element("section", "detail-section");
    section.append(sectionHeading("STATS", "📊 スタッツ"));

    const card = app.element("div", "stats-card glass-card");

    // チーム名の対比ヘッダー (左=ホーム / 右=アウェイ)
    const head = app.element("div", "stats-head");
    head.append(
      app.element("span", "stats-team stat-home", match.home_ja || match.home),
      app.element("span", "stats-team-vs", "VS"),
      app.element("span", "stats-team stat-away", match.away_ja || match.away),
    );
    card.append(head);

    if (isNumber(home.possession) || isNumber(away.possession)) {
      card.append(possessionBlock(home.possession, away.possession));
    }

    const rows = app.element("div", "stat-rows");
    const definitions = [
      ["シュート", home.shots, away.shots],
      ["枠内シュート", home.shots_on_target, away.shots_on_target],
      ["パス", passLabel(home), passLabel(away)],
      ["CK", home.corners, away.corners],
      ["ファウル", home.fouls, away.fouls],
      ["オフサイド", home.offsides, away.offsides],
      ["警告", home.yellow, away.yellow],
      ["退場", home.red, away.red],
    ];
    definitions.forEach(([label, homeValue, awayValue]) => {
      const value = (input) => (isNumber(input) || typeof input === "string" ? input : null);
      const row = statRow(label, value(homeValue), value(awayValue));
      if (row) {
        rows.append(row);
      }
    });
    card.append(rows);

    section.append(card);
    return section;
  }
});
