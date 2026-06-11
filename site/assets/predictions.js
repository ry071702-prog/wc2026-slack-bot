document.addEventListener("DOMContentLoaded", async () => {
  "use strict";

  const app = window.SiteApp;
  const container = document.querySelector("#prediction-chart");
  const totalNode = document.querySelector("#prediction-total");

  try {
    const [data, teams] = await Promise.all([
      app.fetchJson("data/predictions.json", { optional: true }),
      app.fetchJson("data/teams.json").catch(() => null),
    ]);
    const flagByJaName = new Map(
      Array.isArray(teams)
        ? teams.map((team) => [team.name_ja || team.name, team.name])
        : [],
    );
    container.setAttribute("aria-busy", "false");

    const entries = Object.entries(data?.distribution || {})
      .filter(([, count]) => Number(count) > 0)
      .sort((left, right) => Number(right[1]) - Number(left[1]));
    if (entries.length === 0) {
      showEmpty();
      return;
    }

    const total =
      Number(data.total) ||
      entries.reduce((sum, [, count]) => sum + Number(count), 0);
    totalNode.textContent = `${total}票`;
    container.replaceChildren(
      ...entries.map(([team, count]) =>
        createBar(team, Number(count), total, flagByJaName.get(team)),
      ),
    );
  } catch (error) {
    app.logDataError(error);
    app.showLoadError(container);
  }

  function showEmpty() {
    totalNode.textContent = "";
    container.replaceChildren(
      app.emptyState(
        "まだ予想がありません",
        "Slackで /yosou と入力して、最初の予想を登録しましょう。",
      ),
    );
  }

  function createBar(team, count, total, englishName) {
    const row = app.element("div", "chart-row");
    const percentage = total > 0 ? (count / total) * 100 : 0;
    const label = app.element("div", "chart-label");
    const teamText = englishName
      ? `${app.flagEmoji(englishName)} ${team}`
      : team;
    label.append(
      app.element("span", "", teamText),
      app.element("span", "", `${count}票 (${percentage.toFixed(0)}%)`),
    );
    const track = app.element("div", "chart-track");
    const bar = app.element("div", "chart-bar");
    bar.style.setProperty("--bar-width", `${percentage}%`);
    track.append(bar);
    row.append(label, track);
    return row;
  }
});
