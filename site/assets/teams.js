document.addEventListener("DOMContentLoaded", async () => {
  "use strict";

  const app = window.SiteApp;
  const container = document.querySelector("#teams");

  try {
    const teams = await app.fetchJson("data/teams.json");
    container.replaceChildren(...teams.map(createTeamCard));
  } catch (error) {
    app.logDataError(error);
  }

  function createTeamCard(team) {
    const card = app.element("details", "team-card");
    const summary = app.element("summary", "team-summary");
    const title = app.element("h2", "team-title", team.name_ja || team.name);
    title.append(app.element("span", "team-english", team.name));
    const rank = Number.isInteger(team.rank)
      ? `FIFA ${team.rank}位`
      : "FIFAランク 準備中";
    summary.append(title, app.element("span", "rank-badge", rank));
    card.append(summary);

    if (!Array.isArray(team.squad) || team.squad.length === 0) {
      card.append(
        app.element("p", "squad-empty", "選手データ準備中"),
      );
      return card;
    }

    const squad = app.element("div", "squad");
    team.squad
      .slice()
      .sort(
        (left, right) =>
          (Number(left.number) || 999) - (Number(right.number) || 999),
      )
      .forEach((player) => {
        const row = app.element("div", "player-row");
        row.append(
          app.element(
            "span",
            "player-number",
            player.number == null ? "−" : String(player.number),
          ),
          app.element("span", "player-position", player.position || "−"),
          app.element(
            "span",
            "player-name",
            player.name_ja || player.name || "未定",
          ),
        );
        squad.append(row);
      });
    card.append(squad);
    return card;
  }
});
