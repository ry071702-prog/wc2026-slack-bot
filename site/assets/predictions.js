document.addEventListener("DOMContentLoaded", async () => {
  "use strict";

  const app = window.SiteApp;
  const container = document.querySelector("#prediction-chart");
  const totalNode = document.querySelector("#prediction-total");

  try {
    const data = await app.fetchJson("data/predictions.json", {
      optional: true,
    });
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
      ...entries.map(([team, count]) => createBar(team, Number(count), total)),
    );
  } catch (error) {
    app.logDataError(error);
  }

  function showEmpty() {
    totalNode.textContent = "";
    container.replaceChildren(
      app.element("p", "empty-state", "まだ予想がありません"),
    );
  }

  function createBar(team, count, total) {
    const row = app.element("div", "chart-row");
    const percentage = total > 0 ? (count / total) * 100 : 0;
    const label = app.element("div", "chart-label");
    label.append(
      app.element("span", "", team),
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
