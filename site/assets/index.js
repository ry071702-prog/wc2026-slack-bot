document.addEventListener("DOMContentLoaded", async () => {
  "use strict";

  const app = window.SiteApp;

  setupStatCountUp();

  try {
    const schedule = await app.fetchJson("data/schedule.json");
    renderHeadline(schedule);
    renderNextJapan(schedule);
    renderToday(schedule);
    renderResults(schedule);
  } catch (error) {
    app.logDataError(error);
    app.showLoadError(document.querySelector("#next-japan"));
    app.showLoadError(document.querySelector("#today-matches"));
    app.showLoadError(document.querySelector("#recent-results"));
  }

  try {
    const teams = await app.fetchJson("data/teams.json");
    renderTeamsPreview(teams);
  } catch (error) {
    app.logDataError(error);
    app.showLoadError(document.querySelector("#teams-preview"));
  }

  // 一面の見出しをその日の実データで組む (失敗時は静的コピーのまま)
  function renderHeadline(schedule) {
    const node = document.querySelector("#hero-headline");
    if (!node || !Array.isArray(schedule) || schedule.length === 0) {
      return;
    }
    const liveStatuses = new Set(["IN_PLAY", "PAUSED"]);
    const today = app.jstDateKey();
    const todays = schedule.filter((match) => match.date_jst === today);

    const setHeadline = (before, markerText, after) => {
      const marker = app.element("span", "marker", markerText);
      node.replaceChildren(before, marker, after);
    };

    // 1. 日本戦 (進行中 > 今日開催)
    const japanToday = todays.find((match) => match.is_japan);
    if (japanToday && liveStatuses.has(japanToday.status)) {
      setHeadline("いま、", "日本戦", "が進行中");
      return;
    }
    if (japanToday && japanToday.status !== "FINISHED") {
      setHeadline(
        `きょう ${app.formatKickoff(japanToday.kickoff_jst)}、`,
        "日本戦",
        "キックオフ",
      );
      return;
    }

    // 2. 決勝が終わっていれば優勝国
    const finalMatch = schedule.find((match) => match.stage === "FINAL");
    if (finalMatch && finalMatch.status === "FINISHED") {
      const winner = finalWinnerName(finalMatch);
      if (winner) {
        setHeadline("優勝は、", winner, "");
        return;
      }
    }

    // 3. いま試合中
    const liveNow = todays.find((match) => liveStatuses.has(match.status));
    if (liveNow) {
      setHeadline("いま、", liveNow.stage_ja || "試合", "が進行中");
      return;
    }

    // 4. 今日の試合
    if (todays.length > 0) {
      const stages = [
        ...new Set(todays.map((match) => match.stage_ja).filter(Boolean)),
      ];
      if (stages.length === 1) {
        setHeadline("きょうは", stages[0], `、${todays.length}試合`);
      } else {
        setHeadline("きょうは", `${todays.length}試合`, "キックオフ");
      }
      return;
    }

    // 5. 開幕前 (1試合も終わっていない) はカウントダウン
    const upcoming = schedule
      .filter((match) => app.isUpcoming(match))
      .sort(
        (left, right) =>
          new Date(left.kickoff_jst) - new Date(right.kickoff_jst),
      );
    const hasFinished = schedule.some((match) => match.status === "FINISHED");
    if (!hasFinished && upcoming.length > 0) {
      const days = daysUntil(upcoming[0].date_jst, today);
      if (days > 0) {
        setHeadline("開幕まで、あと", `${days}日`, "");
        return;
      }
    }

    // 6. 中休み (次の試合日)
    if (upcoming.length > 0) {
      const next = upcoming[0];
      setHeadline(
        "次の試合は",
        app.formatDay(next.date_jst),
        `　${next.stage_ja || ""}`,
      );
      return;
    }

    // 7. 全日程終了
    setHeadline("大会は", "閉幕", "　また4年後に");
  }

  function finalWinnerName(match) {
    const score = match.score || {};
    if (score.home == null || score.away == null) {
      return null;
    }
    if (score.home !== score.away) {
      return score.home > score.away
        ? match.home_ja || match.home
        : match.away_ja || match.away;
    }
    if (score.penalties_home != null && score.penalties_away != null) {
      return score.penalties_home > score.penalties_away
        ? match.home_ja || match.home
        : match.away_ja || match.away;
    }
    return null;
  }

  function daysUntil(dateKey, todayKey) {
    const target = new Date(`${dateKey}T00:00:00+09:00`);
    const base = new Date(`${todayKey}T00:00:00+09:00`);
    return Math.round((target - base) / 86400000);
  }

  // ステータスボードの数値をスコアボード風にカウントアップ
  function setupStatCountUp() {
    const counters = document.querySelectorAll(".stat-value[data-count]");
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    if (
      counters.length === 0 ||
      reduceMotion ||
      !("IntersectionObserver" in window)
    ) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) {
            return;
          }
          observer.unobserve(entry.target);
          animateCount(entry.target, Number(entry.target.dataset.count));
        });
      },
      { threshold: 0.5 },
    );
    counters.forEach((node) => observer.observe(node));
  }

  function animateCount(node, target) {
    if (!Number.isFinite(target)) {
      return;
    }
    const duration = 900;
    const started = performance.now();
    const tick = (now) => {
      const progress = Math.min((now - started) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      node.textContent = String(Math.round(target * eased));
      if (progress < 1) {
        window.requestAnimationFrame(tick);
      }
    };
    window.requestAnimationFrame(tick);
  }

  function findNextJapanMatch(schedule) {
    return schedule
      .filter((match) => match.is_japan && app.isUpcoming(match))
      .sort(
        (left, right) =>
          new Date(left.kickoff_jst) - new Date(right.kickoff_jst),
      )[0];
  }

  function renderHeroMini(nextMatch) {
    const mini = document.querySelector("#hero-next-mini");
    if (!mini || !nextMatch) {
      return;
    }
    mini.querySelector(".hero-mini-match").textContent = [
      `${app.flagEmoji(nextMatch.home)} ${nextMatch.home_ja || nextMatch.home}`,
      "vs",
      `${app.flagEmoji(nextMatch.away)} ${nextMatch.away_ja || nextMatch.away}`,
    ].join(" ");
    mini.querySelector(".hero-mini-kickoff").textContent =
      `${app.formatFullKickoff(nextMatch.kickoff_jst)} キックオフ (日本時間)`;
    mini.hidden = false;
  }

  function heroTeam(name, displayName) {
    const node = app.element("div", "hmc-team");
    const flag = app.element("span", "hmc-team-flag", app.flagEmoji(name));
    flag.setAttribute("aria-hidden", "true");
    node.append(flag, app.element("span", "hmc-team-name", displayName || name));
    return node;
  }

  function renderNextJapan(schedule) {
    const container = document.querySelector("#next-japan");
    const nextMatch = findNextJapanMatch(schedule);
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

    renderHeroMini(nextMatch);

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
    // 日本代表特設ページへの導線
    const japanLink = app.element(
      "a",
      "hmc-japan-link",
      "🇯🇵 日本代表 特設ページ ▸",
    );
    japanLink.href = "japan.html";
    info.append(japanLink);

    const versus = app.element("div", "hmc-versus");
    versus.append(
      heroTeam(nextMatch.home, nextMatch.home_ja),
      app.element("span", "hmc-vs", "VS"),
      heroTeam(nextMatch.away, nextMatch.away_ja),
    );

    const countdown = app.element("div", "hmc-countdown");
    countdown.append(
      app.element("p", "hmc-countdown-label", "KICKOFF IN"),
    );
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

  function renderToday(schedule) {
    const container = document.querySelector("#today-matches");
    container.setAttribute("aria-busy", "false");
    const today = app.jstDateKey();
    const matches = schedule.filter((match) => match.date_jst === today);
    if (matches.length === 0) {
      container.replaceChildren(
        app.emptyState(
          "今日の試合はありません",
          "次の試合日程をチェックして、観戦予定を立てましょう。",
        ),
      );
      return;
    }
    container.replaceChildren(
      ...matches.map((match) => app.createMatchCard(match)),
    );
  }

  function renderResults(schedule) {
    const container = document.querySelector("#recent-results");
    container.setAttribute("aria-busy", "false");
    const results = schedule
      .filter((match) => match.status === "FINISHED")
      .sort(
        (left, right) =>
          new Date(right.kickoff_jst) - new Date(left.kickoff_jst),
      )
      .slice(0, 6);
    if (results.length === 0) {
      container.replaceChildren(
        app.emptyState(
          "試合結果はまだありません",
          "大会が始まると、ここに最新の結果が表示されます。",
        ),
      );
      return;
    }
    container.replaceChildren(
      ...results.map((match) => app.createMatchCard(match)),
    );
  }

  function renderTeamsPreview(teams) {
    const container = document.querySelector("#teams-preview");
    container.setAttribute("aria-busy", "false");
    if (!Array.isArray(teams) || teams.length === 0) {
      container.replaceChildren(
        app.emptyState("出場国データを準備中です"),
      );
      return;
    }

    const japan = teams.find((team) => team.name === "Japan");
    const ranked = teams
      .filter((team) => team.name !== "Japan" && Number.isInteger(team.rank))
      .sort((left, right) => left.rank - right.rank)
      .slice(0, japan ? 5 : 6);
    const featured = japan ? [japan, ...ranked] : ranked;

    container.replaceChildren(
      ...featured.map((team) => {
        const card = app.element("a", "team-preview-card glass-card");
        card.href = "teams.html";
        const flag = app.element(
          "span",
          "team-preview-flag",
          app.flagEmoji(team.name),
        );
        flag.setAttribute("aria-hidden", "true");
        card.append(
          flag,
          app.element("p", "team-preview-name", team.name_ja || team.name),
          app.element(
            "span",
            "rank-badge",
            Number.isInteger(team.rank)
              ? `FIFA ${team.rank}位`
              : "ランク準備中",
          ),
        );
        return card;
      }),
    );
  }
});
