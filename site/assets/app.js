(() => {
  "use strict";

  // CSS の .reveal (fade-up) は JS が動く環境でのみ適用する
  document.documentElement.classList.add("js");

  const JST_TIME_ZONE = "Asia/Tokyo";
  const scheduledStatuses = new Set(["SCHEDULED", "TIMED"]);
  const liveStatuses = new Set(["IN_PLAY", "PAUSED"]);

  const FLAG_EMOJI = {
    Algeria: "🇩🇿",
    Argentina: "🇦🇷",
    Australia: "🇦🇺",
    Austria: "🇦🇹",
    Belgium: "🇧🇪",
    "Bosnia-Herzegovina": "🇧🇦",
    Brazil: "🇧🇷",
    Canada: "🇨🇦",
    "Cape Verde Islands": "🇨🇻",
    Colombia: "🇨🇴",
    "Congo DR": "🇨🇩",
    Croatia: "🇭🇷",
    "Curaçao": "🇨🇼",
    Czechia: "🇨🇿",
    Ecuador: "🇪🇨",
    Egypt: "🇪🇬",
    England: "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    France: "🇫🇷",
    Germany: "🇩🇪",
    Ghana: "🇬🇭",
    Haiti: "🇭🇹",
    Iran: "🇮🇷",
    Iraq: "🇮🇶",
    "Ivory Coast": "🇨🇮",
    Japan: "🇯🇵",
    Jordan: "🇯🇴",
    Mexico: "🇲🇽",
    Morocco: "🇲🇦",
    Netherlands: "🇳🇱",
    "New Zealand": "🇳🇿",
    Norway: "🇳🇴",
    Panama: "🇵🇦",
    Paraguay: "🇵🇾",
    Portugal: "🇵🇹",
    Qatar: "🇶🇦",
    "Saudi Arabia": "🇸🇦",
    Scotland: "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    Senegal: "🇸🇳",
    "South Africa": "🇿🇦",
    "South Korea": "🇰🇷",
    Spain: "🇪🇸",
    Sweden: "🇸🇪",
    Switzerland: "🇨🇭",
    Tunisia: "🇹🇳",
    Turkey: "🇹🇷",
    "United States": "🇺🇸",
    Uruguay: "🇺🇾",
    Uzbekistan: "🇺🇿",
  };

  function flagEmoji(name) {
    return FLAG_EMOJI[name] || "⚽";
  }

  // FIFAランク差からのざっくり勝率 (ロジスティック)。番号が小さいほど格上。
  // 返り値: {home, away} の整数% (合計100)。どちらかのランクが無ければ null。
  function winProbability(rankHome, rankAway) {
    if (!Number.isFinite(rankHome) || !Number.isFinite(rankAway)) {
      return null;
    }
    const k = 0.08;
    const pHome = 1 / (1 + Math.exp(-k * (rankAway - rankHome)));
    let home = Math.round(pHome * 100);
    home = Math.min(97, Math.max(3, home));
    return { home, away: 100 - home };
  }

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

  function pill(text, variant) {
    return element("span", `pill pill-${variant}`, text);
  }

  function teamLabel(name, displayName, extraClass) {
    const wrapper = element(
      "span",
      extraClass ? `team-name ${extraClass}` : "team-name",
    );
    const flag = element("span", "team-flag", flagEmoji(name));
    flag.setAttribute("aria-hidden", "true");
    wrapper.append(flag, element("span", "team-label", displayName || name));
    return wrapper;
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
    if (liveStatuses.has(match.status)) {
      return "試合中";
    }
    return "開始前";
  }

  function statusPill(match) {
    if (liveStatuses.has(match.status)) {
      return pill("LIVE", "live");
    }
    if (match.status === "FINISHED") {
      return pill("FULL TIME", "finished");
    }
    return pill("予定", "next");
  }

  function winnerSide(match) {
    if (match.status !== "FINISHED") {
      return null;
    }
    const score = match.score || {};
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

  function createMatchCard(match) {
    const classNames = ["match-card", "glass-card"];
    if (match.is_japan) {
      classNames.push("is-japan");
    }
    if (match.status === "FINISHED") {
      classNames.push("is-finished");
    }
    if (liveStatuses.has(match.status)) {
      classNames.push("is-live");
    }
    // カード全体を試合詳細ページへのリンクにする
    const card = element("a", classNames.join(" "));
    card.href = `match.html?id=${encodeURIComponent(match.id)}`;

    const top = element("div", "match-card-top");
    top.append(
      element("time", "match-time", formatKickoff(match.kickoff_jst)),
      statusPill(match),
    );

    const winner = winnerSide(match);
    const matchup = element("div", "matchup");
    matchup.append(
      teamLabel(
        match.home,
        match.home_ja || match.home,
        winner === "home" ? "is-winner" : "",
      ),
      element("span", "match-score", scoreText(match)),
      teamLabel(
        match.away,
        match.away_ja || match.away,
        winner === "away" ? "is-winner" : "",
      ),
    );

    const bottom = element("div", "match-card-bottom");
    bottom.append(
      element("span", "match-stage", match.stage_ja || "ステージ未定"),
    );
    const detail = statusText(match);
    if (detail.includes("PK") || detail.includes("延長")) {
      bottom.append(element("span", "match-extra", detail));
    }
    if (match.is_japan) {
      bottom.append(pill("JAPAN MATCH", "japan"));
    }
    bottom.append(element("span", "match-cta", "詳細 ▸"));

    card.append(top, matchup, bottom);
    return card;
  }

  function isUpcoming(match, now = new Date()) {
    return (
      scheduledStatuses.has(match.status) &&
      new Date(match.kickoff_jst).getTime() > now.getTime()
    );
  }

  function formatGroup(group) {
    if (!group || typeof group !== "string") {
      return "";
    }
    const parts = group.split("_");
    return parts.length === 2 ? `グループ${parts[1]}` : group;
  }

  function emptyState(title, note) {
    const box = element("div", "empty-state glass-card");
    box.append(element("p", "empty-state-title", title));
    if (note) {
      box.append(element("p", "empty-state-note", note));
    }
    return box;
  }

  function showLoadError(container) {
    if (!container) {
      return;
    }
    container.setAttribute("aria-busy", "false");
    container.replaceChildren(
      emptyState(
        "データを取得できませんでした",
        "時間をおいてからページを再読み込みしてください。",
      ),
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

  function setupReveal() {
    const targets = document.querySelectorAll(".reveal");
    if (targets.length === 0) {
      return;
    }
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    if (reduceMotion || !("IntersectionObserver" in window)) {
      targets.forEach((node) => node.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.05 },
    );
    targets.forEach((node) => observer.observe(node));
  }

  window.SiteApp = {
    activateNavigation,
    createMatchCard,
    element,
    emptyState,
    fetchJson,
    flagEmoji,
    formatDay,
    formatFullKickoff,
    formatGroup,
    formatKickoff,
    isUpcoming,
    jstDateKey,
    logDataError,
    pill,
    showLoadError,
    statusText,
    teamLabel,
    winProbability,
  };

  document.addEventListener("DOMContentLoaded", () => {
    activateNavigation();
    setupReveal();
  });
})();
