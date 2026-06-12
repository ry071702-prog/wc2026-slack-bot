(() => {
  "use strict";

  // 集計対象: 確定 (FINISHED) + 暫定 (IN_PLAY / PAUSED は LIVE マーク付き)
  const COUNTABLE_STATUSES = new Set(["FINISHED", "IN_PLAY", "PAUSED"]);
  const LIVE_STATUSES = new Set(["IN_PLAY", "PAUSED"]);

  function createRow(team, teamJa) {
    return {
      team,
      team_ja: teamJa || team,
      played: 0,
      won: 0,
      drawn: 0,
      lost: 0,
      gf: 0,
      ga: 0,
      gd: 0,
      points: 0,
      live: false,
      rank: 0,
    };
  }

  function applyResult(row, goalsFor, goalsAgainst, isLive) {
    row.played += 1;
    row.gf += goalsFor;
    row.ga += goalsAgainst;
    row.gd = row.gf - row.ga;
    if (goalsFor > goalsAgainst) {
      row.won += 1;
      row.points += 3;
    } else if (goalsFor === goalsAgainst) {
      row.drawn += 1;
      row.points += 1;
    } else {
      row.lost += 1;
    }
    if (isLive) {
      row.live = true;
    }
  }

  // 並び順: 勝ち点 → 得失点差 → 総得点 → チーム名 (FIFA公式の直接対決等は簡略化)
  function compareRows(a, b) {
    if (b.points !== a.points) {
      return b.points - a.points;
    }
    if (b.gd !== a.gd) {
      return b.gd - a.gd;
    }
    if (b.gf !== a.gf) {
      return b.gf - a.gf;
    }
    return a.team < b.team ? -1 : a.team > b.team ? 1 : 0;
  }

  /**
   * schedule.json の全試合からグループ順位表を集計する純関数。
   * 戻り値: [{ group: "GROUP_A", teams: [row, ...] }, ...] (A→L 順 / 各組順位順)
   */
  function computeStandings(matches) {
    const groups = new Map();

    for (const match of matches || []) {
      if (match.stage !== "GROUP_STAGE" || !match.group) {
        continue;
      }
      if (!groups.has(match.group)) {
        groups.set(match.group, new Map());
      }
      const teams = groups.get(match.group);
      if (match.home && !teams.has(match.home)) {
        teams.set(match.home, createRow(match.home, match.home_ja));
      }
      if (match.away && !teams.has(match.away)) {
        teams.set(match.away, createRow(match.away, match.away_ja));
      }

      const score = match.score || {};
      if (
        !COUNTABLE_STATUSES.has(match.status) ||
        !Number.isInteger(score.home) ||
        !Number.isInteger(score.away) ||
        !match.home ||
        !match.away
      ) {
        continue;
      }
      const isLive = LIVE_STATUSES.has(match.status);
      applyResult(teams.get(match.home), score.home, score.away, isLive);
      applyResult(teams.get(match.away), score.away, score.home, isLive);
    }

    const result = [];
    for (const groupId of [...groups.keys()].sort()) {
      const rows = [...groups.get(groupId).values()].sort(compareRows);
      rows.forEach((row, index) => {
        row.rank = index + 1;
      });
      result.push({ group: groupId, teams: rows });
    }
    return result;
  }

  /**
   * 各組3位を抜き出して比較順 (勝ち点→得失点差→総得点) に並べる純関数。
   * 上位8チーム (qualifies=true) がラウンド32へ進出。
   */
  function rankThirdPlace(standings, slots = 8) {
    const thirds = (standings || [])
      .filter((entry) => entry.teams.length >= 3)
      .map((entry) => ({ ...entry.teams[2], group: entry.group }));
    thirds.sort(compareRows);
    return thirds.map((row, index) => ({
      ...row,
      rank: index + 1,
      qualifies: index < slots,
    }));
  }

  // Node (node --test / node -e) から検証できるようにエクスポート
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { computeStandings, rankThirdPlace };
    return;
  }

  /* ----------------------------------------------------------------------
     以下はブラウザ専用の描画コード
     ---------------------------------------------------------------------- */

  function groupLetter(groupId) {
    const parts = String(groupId || "").split("_");
    return parts.length === 2 ? parts[1] : groupId;
  }

  function signedGd(value) {
    return value > 0 ? `+${value}` : String(value);
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const app = window.SiteApp;
    const standingsContainer = document.querySelector("#standings");
    const thirdContainer = document.querySelector("#third-place");

    let schedule = [];
    try {
      schedule = await app.fetchJson("data/schedule.json");
    } catch (error) {
      app.logDataError(error);
      app.showLoadError(standingsContainer);
      app.showLoadError(thirdContainer);
      return;
    }

    const standings = computeStandings(schedule);
    const thirds = rankThirdPlace(standings);

    standingsContainer.setAttribute("aria-busy", "false");
    thirdContainer.setAttribute("aria-busy", "false");

    if (standings.length === 0) {
      standingsContainer.replaceChildren(
        app.emptyState(
          "グループステージのデータがありません",
          "時間をおいてからページを再読み込みしてください。",
        ),
      );
      thirdContainer.replaceChildren();
      return;
    }

    standingsContainer.replaceChildren(
      ...standings.map((entry) => createGroupCard(entry)),
    );
    thirdContainer.replaceChildren(createThirdPlaceCard(thirds));

    function teamCell(row) {
      const cell = app.element("td", "st-team-cell");
      const wrapper = app.element("span", "st-team");
      const flag = app.element("span", "st-flag", app.flagEmoji(row.team));
      flag.setAttribute("aria-hidden", "true");
      wrapper.append(flag, app.element("span", "st-name", row.team_ja));
      if (row.live) {
        wrapper.append(app.element("span", "st-live", "LIVE"));
      }
      cell.append(wrapper);
      return cell;
    }

    function numberCells(row) {
      return [
        app.element("td", "", String(row.played)),
        app.element("td", "", String(row.won)),
        app.element("td", "", String(row.drawn)),
        app.element("td", "", String(row.lost)),
        app.element("td", "st-gd", signedGd(row.gd)),
        app.element("td", "st-pts", String(row.points)),
      ];
    }

    function headerRow(labels) {
      const tr = app.element("tr");
      labels.forEach(([label, className]) => {
        const th = app.element("th", className || "", label);
        th.setAttribute("scope", "col");
        tr.append(th);
      });
      return tr;
    }

    function createGroupCard(entry) {
      const hasJapan = entry.teams.some((row) => row.team === "Japan");
      const card = app.element(
        "section",
        hasJapan
          ? "standings-card glass-card is-japan"
          : "standings-card glass-card",
      );

      const head = app.element("div", "standings-card-head");
      head.append(
        app.element("h3", "standings-card-title", app.formatGroup(entry.group)),
      );
      if (hasJapan) {
        head.append(app.pill("JAPAN", "japan"));
      }
      card.append(head);

      const table = app.element("table", "st-table");
      const thead = app.element("thead");
      thead.append(
        headerRow([
          ["#", "st-col-rank"],
          ["国", "st-col-team"],
          ["試", "st-col-num"],
          ["勝", "st-col-num"],
          ["分", "st-col-num"],
          ["負", "st-col-num"],
          ["得失", "st-col-gd"],
          ["勝点", "st-col-pts"],
        ]),
      );
      const tbody = app.element("tbody");
      entry.teams.forEach((row) => {
        const classNames = [];
        if (row.rank <= 2) {
          classNames.push("is-qualify");
        }
        if (row.rank === 3) {
          classNames.push("is-third");
        }
        const tr = app.element("tr", classNames.join(" "));
        const rankCell = app.element("td", "st-rank");
        if (row.rank === 3) {
          rankCell.append(app.element("span", "st-badge-third", "3位"));
        } else {
          rankCell.textContent = String(row.rank);
        }
        tr.append(rankCell, teamCell(row), ...numberCells(row));
        tbody.append(tr);
      });
      table.append(thead, tbody);
      card.append(table);
      return card;
    }

    function createThirdPlaceCard(rows) {
      const card = app.element("div", "standings-card third-place-card glass-card");
      const table = app.element("table", "st-table");
      const thead = app.element("thead");
      thead.append(
        headerRow([
          ["#", "st-col-rank"],
          ["組", "st-col-group"],
          ["国", "st-col-team"],
          ["試", "st-col-num"],
          ["得失", "st-col-gd"],
          ["得点", "st-col-gd"],
          ["勝点", "st-col-pts"],
        ]),
      );
      const tbody = app.element("tbody");
      rows.forEach((row) => {
        const tr = app.element("tr", row.qualifies ? "is-qualify" : "");
        tr.append(
          app.element("td", "st-rank", String(row.rank)),
          app.element("td", "st-group", groupLetter(row.group)),
          teamCell(row),
          app.element("td", "", String(row.played)),
          app.element("td", "st-gd", signedGd(row.gd)),
          app.element("td", "", String(row.gf)),
          app.element("td", "st-pts", String(row.points)),
        );
        tbody.append(tr);
      });
      table.append(thead, tbody);
      card.append(table);
      return card;
    }
  });
})();
