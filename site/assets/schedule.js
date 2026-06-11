document.addEventListener("DOMContentLoaded", async () => {
  "use strict";

  const app = window.SiteApp;
  const container = document.querySelector("#schedule");
  const toggle = document.querySelector("#japan-only");
  let schedule = [];

  try {
    schedule = await app.fetchJson("data/schedule.json");
    container.setAttribute("aria-busy", "false");
    render();
    toggle.addEventListener("change", render);
  } catch (error) {
    app.logDataError(error);
    app.showLoadError(container);
  }

  function render() {
    const visibleMatches = toggle.checked
      ? schedule.filter((match) => match.is_japan)
      : schedule;
    if (visibleMatches.length === 0) {
      container.replaceChildren(
        app.emptyState(
          "該当する試合はありません",
          "フィルタ条件を変えて確認してみてください。",
        ),
      );
      return;
    }

    const groups = new Map();
    visibleMatches.forEach((match) => {
      const matches = groups.get(match.date_jst) || [];
      matches.push(match);
      groups.set(match.date_jst, matches);
    });

    const fragments = [];
    groups.forEach((matches, dateKey) => {
      const section = app.element("section", "date-group");
      section.append(
        app.element("h2", "date-heading", app.formatDay(dateKey)),
      );
      const list = app.element("div", "match-list");
      list.append(...matches.map((match) => app.createMatchCard(match)));
      section.append(list);
      fragments.push(section);
    });
    container.replaceChildren(...fragments);
  }
});
