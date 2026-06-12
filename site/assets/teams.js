document.addEventListener("DOMContentLoaded", async () => {
  "use strict";

  const app = window.SiteApp;
  const container = document.querySelector("#teams");
  const searchInput = document.querySelector("#team-search");
  const sortSelect = document.querySelector("#team-sort");

  let teams = [];
  let groupByTeam = new Map();

  try {
    const [teamData, schedule] = await Promise.all([
      app.fetchJson("data/teams.json"),
      app.fetchJson("data/schedule.json").catch(() => null),
    ]);
    teams = teamData;
    groupByTeam = buildGroupMap(schedule);
    container.setAttribute("aria-busy", "false");
    render();
    searchInput.addEventListener("input", render);
    sortSelect.addEventListener("change", render);
  } catch (error) {
    app.logDataError(error);
    app.showLoadError(container);
  }

  function buildGroupMap(schedule) {
    const map = new Map();
    if (!Array.isArray(schedule)) {
      return map;
    }
    schedule.forEach((match) => {
      if (!match.group) {
        return;
      }
      [match.home, match.away].forEach((name) => {
        if (name && name !== "TBD" && !map.has(name)) {
          map.set(name, match.group);
        }
      });
    });
    return map;
  }

  function sortedTeams(list) {
    const key = sortSelect.value;
    const collator = new Intl.Collator("ja");
    return list.slice().sort((left, right) => {
      if (key === "name") {
        return collator.compare(
          left.name_ja || left.name,
          right.name_ja || right.name,
        );
      }
      if (key === "group") {
        const leftGroup = groupByTeam.get(left.name) || "ZZZ";
        const rightGroup = groupByTeam.get(right.name) || "ZZZ";
        if (leftGroup !== rightGroup) {
          return leftGroup < rightGroup ? -1 : 1;
        }
        return (left.rank ?? 999) - (right.rank ?? 999);
      }
      return (left.rank ?? 999) - (right.rank ?? 999);
    });
  }

  function render() {
    const query = (searchInput.value || "").trim().toLowerCase();
    const visible = sortedTeams(
      teams.filter((team) => {
        if (!query) {
          return true;
        }
        return (
          (team.name_ja || "").toLowerCase().includes(query) ||
          (team.name || "").toLowerCase().includes(query)
        );
      }),
    );

    if (visible.length === 0) {
      container.replaceChildren(
        app.emptyState(
          "該当する国が見つかりません",
          "キーワードを変えて検索してみてください。",
        ),
      );
      return;
    }
    container.replaceChildren(...visible.map(createTeamCard));
  }

  function createHistoryRow(history) {
    const row = app.element("div", "team-history");
    if (!history) {
      return row;
    }
    if (history.note) {
      row.title = history.note;
    }

    if (Number.isInteger(history.appearances) && history.appearances > 0) {
      row.append(
        app.element(
          "span",
          "history-badge",
          `出場${history.appearances}回目`,
        ),
      );
    }
    if (Number.isInteger(history.titles) && history.titles > 0) {
      const titles = app.element(
        "span",
        "history-badge is-gold",
        `優勝${history.titles}回`,
      );
      if (Array.isArray(history.title_years) && history.title_years.length > 0) {
        titles.title = `優勝: ${history.title_years.join(", ")}`;
      }
      row.append(titles);
    }
    if (history.best) {
      row.append(app.element("span", "history-badge", `最高: ${history.best}`));
    }
    if (history.last && history.last.year) {
      row.append(
        app.element(
          "span",
          "history-badge",
          `前回: ${history.last.year} ${history.last.result || ""}`.trim(),
        ),
      );
    } else {
      row.append(app.element("span", "history-badge is-debut", "初出場"));
    }
    if (history.note) {
      row.append(app.element("span", "history-note", `※ ${history.note}`));
    }
    return row;
  }

  function createAvatarFallback(player) {
    const fallback = app.element(
      "span",
      "player-avatar-fallback",
      player.number == null ? "−" : String(player.number),
    );
    fallback.setAttribute("aria-hidden", "true");
    return fallback;
  }

  function createAvatar(player) {
    const avatar = app.element("span", "player-avatar");
    if (player.photo) {
      const img = document.createElement("img");
      img.className = "player-avatar-img";
      img.src = player.photo;
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.referrerPolicy = "no-referrer";
      img.addEventListener("error", () => {
        avatar.replaceChildren(createAvatarFallback(player));
      });
      avatar.append(img);
    } else {
      avatar.append(createAvatarFallback(player));
    }
    return avatar;
  }

  function createTeamCard(team) {
    const card = app.element("details", "team-card glass-card");
    const summary = app.element("summary", "team-summary");

    const flag = app.element("span", "team-flag-lg", app.flagEmoji(team.name));
    flag.setAttribute("aria-hidden", "true");

    const heading = app.element("div", "team-heading");
    const title = app.element("h2", "team-title", team.name_ja || team.name);
    title.append(app.element("span", "team-english", team.name));
    heading.append(title);
    if (team.history) {
      heading.append(createHistoryRow(team.history));
    }

    const badges = app.element("div", "team-badges");
    badges.append(
      app.element(
        "span",
        "rank-badge",
        Number.isInteger(team.rank)
          ? `FIFA ${team.rank}位`
          : "FIFAランク 準備中",
      ),
    );
    const groupLabel = app.formatGroup(groupByTeam.get(team.name));
    if (groupLabel) {
      badges.append(app.element("span", "group-badge", groupLabel));
    }

    summary.append(flag, heading, badges);
    card.append(summary);

    if (!Array.isArray(team.squad) || team.squad.length === 0) {
      card.append(app.element("p", "squad-empty", "選手データ準備中"));
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
          createAvatar(player),
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
