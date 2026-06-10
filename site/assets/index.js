document.addEventListener("DOMContentLoaded", async () => {
  "use strict";

  const app = window.SiteApp;
  try {
    const schedule = await app.fetchJson("data/schedule.json");
    renderCountdown(schedule);
    renderToday(schedule);
    renderResults(schedule);
  } catch (error) {
    app.logDataError(error);
  }

  function renderCountdown(schedule) {
    const section = document.querySelector("#next-japan-section");
    const container = document.querySelector("#next-japan");
    const nextMatch = schedule
      .filter((match) => match.is_japan && app.isUpcoming(match))
      .sort(
        (left, right) =>
          new Date(left.kickoff_jst) - new Date(right.kickoff_jst),
      )[0];

    if (!nextMatch) {
      section.hidden = true;
      return;
    }

    const card = app.element("div", "countdown-card");
    card.append(
      app.element("p", "countdown-label", "NEXT JAPAN MATCH"),
      app.element(
        "p",
        "countdown-match",
        `${nextMatch.home_ja} vs ${nextMatch.away_ja}`,
      ),
      app.element(
        "p",
        "countdown-kickoff",
        `${app.formatFullKickoff(nextMatch.kickoff_jst)} キックオフ`,
      ),
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
    card.append(clock);
    container.replaceChildren(card);

    const update = () => {
      const remaining = new Date(nextMatch.kickoff_jst).getTime() - Date.now();
      if (remaining <= 0) {
        section.hidden = true;
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
    window.setInterval(update, 1000);
  }

  function renderToday(schedule) {
    const container = document.querySelector("#today-matches");
    const today = app.jstDateKey();
    const matches = schedule.filter((match) => match.date_jst === today);
    if (matches.length === 0) {
      container.replaceChildren(
        app.element("p", "empty-state", "今日の試合はありません"),
      );
      return;
    }
    container.replaceChildren(
      ...matches.map((match) => app.createMatchCard(match)),
    );
  }

  function renderResults(schedule) {
    const container = document.querySelector("#recent-results");
    const results = schedule
      .filter((match) => match.status === "FINISHED")
      .sort(
        (left, right) =>
          new Date(right.kickoff_jst) - new Date(left.kickoff_jst),
      )
      .slice(0, 5);
    if (results.length === 0) {
      container.replaceChildren(
        app.element("p", "empty-state", "試合結果はまだありません"),
      );
      return;
    }
    container.replaceChildren(
      ...results.map((match) => app.createMatchCard(match)),
    );
  }
});
