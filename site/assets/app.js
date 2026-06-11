(() => {
  "use strict";

  const JST_TIME_ZONE = "Asia/Tokyo";
  const scheduledStatuses = new Set(["SCHEDULED", "TIMED"]);

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, { cache: "no-store" });
    if (options.optional && response.status === 404) {
      return null;
    }
    if (!response.ok) {
      throw new Error(`${url}: ${response.status}`);
    }
    return response.json();
  }

  function jstDateKey(value = new Date()) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: JST_TIME_ZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(value);
    const values = Object.fromEntries(
      parts.map((part) => [part.type, part.value]),
    );
    return `${values.year}-${values.month}-${values.day}`;
  }

  function formatDay(dateKey) {
    return new Intl.DateTimeFormat("ja-JP", {
      timeZone: JST_TIME_ZONE,
      month: "numeric",
      day: "numeric",
      weekday: "short",
    }).format(new Date(`${dateKey}T00:00:00+09:00`));
  }

  function formatKickoff(isoString) {
    return new Intl.DateTimeFormat("ja-JP", {
      timeZone: JST_TIME_ZONE,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(isoString));
  }

  function formatFullKickoff(isoString) {
    return new Intl.DateTimeFormat("ja-JP", {
      timeZone: JST_TIME_ZONE,
      month: "numeric",
      day: "numeric",
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(isoString));
  }

  function element(tagName, className, text) {
    const node = document.createElement(tagName);
    if (className) {
      node.className = className;
    }
    if (text !== undefined) {
      node.textContent = text;
    }
    return node;
  }

  function scoreText(match) {
    if (
      match.status !== "FINISHED" ||
      !Number.isInteger(match.score?.home) ||
      !Number.isInteger(match.score?.away)
    ) {
      return "vs";
    }
    return `${match.score.home} - ${match.score.away}`;
  }

  function statusText(match) {
    if (match.status === "FINISHED") {
      const home = match.score?.penalties_home;
      const away = match.score?.penalties_away;
      if (Number.isInteger(home) && Number.isInteger(away)) {
        return `試合終了 / PK ${home}-${away}`;
      }
      if (match.score?.duration === "EXTRA_TIME") {
        return "試合終了 / 延長";
      }
      return "試合終了";
    }
    if (match.status === "IN_PLAY" || match.status === "PAUSED") {
      return "試合中";
    }
    return "開始前";
  }

  function createMatchCard(match) {
    const classNames = ["match-card"];
    if (match.is_japan) {
      classNames.push("is-japan");
    }
    if (match.status === "FINISHED") {
      classNames.push("is-finished");
    }
    if (match.status === "IN_PLAY" || match.status === "PAUSED") {
      classNames.push("is-live");
    }
    const card = element("article", classNames.join(" "));

    const matchup = element("div", "matchup");
    matchup.append(
      element("span", "team-name", match.home_ja || match.home),
      element("span", "match-score", scoreText(match)),
      element("span", "team-name", match.away_ja || match.away),
    );

    const side = element("div", "match-side");
    side.append(
      element("span", "match-stage", match.stage_ja || "ステージ未定"),
      element("span", "match-status", statusText(match)),
    );

    card.append(
      element("time", "match-time", formatKickoff(match.kickoff_jst)),
      matchup,
      side,
    );
    if (match.is_japan) {
      card.append(element("div", "japan-label", "🇯🇵 日本戦"));
    }
    return card;
  }

  function isUpcoming(match, now = new Date()) {
    return (
      scheduledStatuses.has(match.status) &&
      new Date(match.kickoff_jst).getTime() > now.getTime()
    );
  }

  function logDataError(error) {
    console.error("Site data could not be loaded.", error);
  }

  function activateNavigation() {
    const currentPage = document.body.dataset.page;
    document.querySelectorAll("[data-nav]").forEach((link) => {
      if (link.dataset.nav === currentPage) {
        link.setAttribute("aria-current", "page");
      }
    });
  }

  window.SiteApp = {
    activateNavigation,
    createMatchCard,
    element,
    fetchJson,
    formatDay,
    formatFullKickoff,
    formatKickoff,
    isUpcoming,
    jstDateKey,
    logDataError,
  };

  document.addEventListener("DOMContentLoaded", activateNavigation);
})();
