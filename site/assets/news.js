/* World Cup News — ソースカード + Google News RSS記事 (data/news.json) の描画。
   news.html ではタブ付きフルビュー、index.html では最重要6選のダイジェストを描く。 */
document.addEventListener("DOMContentLoaded", async () => {
  "use strict";

  const app = window.SiteApp;
  const sources = Array.isArray(window.NEWS_SOURCES) ? window.NEWS_SOURCES : [];

  const CATEGORY_LABELS = {
    official: "公式情報",
    breaking: "速報",
    japan: "日本語",
    analysis: "分析・読み物",
    schedule: "日程・結果",
  };

  const RELIABILITY_LABELS = {
    high: "信頼度 High",
    medium: "信頼度 Medium",
  };

  // タブごとの RSS 記事の言語 (記事リストを出すのは速報/日本語のみ)
  const FEED_LANG_BY_CATEGORY = {
    breaking: "en",
    japan: "ja",
  };

  function externalLink(className, href) {
    const link = app.element("a", className);
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  }

  function relativeTime(isoString) {
    const time = new Date(isoString).getTime();
    if (!Number.isFinite(time)) {
      return "";
    }
    const diffMinutes = Math.floor((Date.now() - time) / 60000);
    if (diffMinutes < 1) {
      return "たった今";
    }
    if (diffMinutes < 60) {
      return `${diffMinutes}分前`;
    }
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) {
      return `${diffHours}時間前`;
    }
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 8) {
      return `${diffDays}日前`;
    }
    return new Intl.DateTimeFormat("ja-JP", {
      timeZone: "Asia/Tokyo",
      month: "numeric",
      day: "numeric",
    }).format(new Date(isoString));
  }

  function sourcesFor(category) {
    return sources
      .filter(
        (source) =>
          Array.isArray(source.displayCategory) &&
          source.displayCategory.includes(category),
      )
      .sort((left, right) => {
        if (left.priority !== right.priority) {
          return left.priority - right.priority;
        }
        return sources.indexOf(left) - sources.indexOf(right);
      });
  }

  function createSourceCard(source, categoryLabel) {
    const isOfficial = source.category === "official";
    const card = app.element(
      "article",
      isOfficial ? "news-card glass-card is-official" : "news-card glass-card",
    );

    const top = app.element("div", "news-card-top");
    top.append(app.pill(categoryLabel, "stage"));
    if (isOfficial) {
      top.append(app.element("span", "pill pill-official", "Official"));
    }
    top.append(
      app.element(
        "span",
        `pill pill-reliability-${source.reliability}`,
        RELIABILITY_LABELS[source.reliability] || "信頼度 -",
      ),
    );

    const title = app.element("h3", "news-card-title", source.name);
    const desc = app.element("p", "news-card-desc", source.description);

    const bottom = app.element("div", "news-card-bottom");
    bottom.append(
      app.element(
        "span",
        "news-card-note",
        `${source.language === "ja" ? "日本語" : "English"} / 各メディアで最新情報を確認`,
      ),
    );
    const button = externalLink("neon-btn neon-btn-secondary news-card-btn", source.url);
    button.textContent = "記事を見る";
    bottom.append(button);

    card.append(top, title, desc, bottom);
    return card;
  }

  function createThumbPlaceholder() {
    const placeholder = app.element("span", "news-thumb-placeholder");
    placeholder.setAttribute("aria-hidden", "true");
    placeholder.append(app.element("span", "news-thumb-ball", "⚽"));
    return placeholder;
  }

  function createArticleCard(article) {
    const card = externalLink("news-thumb-card glass-card", article.url);

    const media = app.element("span", "news-thumb-media");
    if (article.image) {
      const img = document.createElement("img");
      img.className = "news-thumb-img";
      img.src = article.image;
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.referrerPolicy = "no-referrer";
      img.addEventListener("error", () => {
        media.replaceChildren(createThumbPlaceholder());
      });
      media.append(img);
    } else {
      media.append(createThumbPlaceholder());
    }
    card.append(media);

    const body = app.element("span", "news-thumb-body");
    body.append(app.element("span", "news-thumb-title", article.title));
    const meta = app.element("span", "news-thumb-meta");
    if (article.source) {
      meta.append(app.element("span", "news-thumb-source", article.source));
    }
    if (article.published_at) {
      meta.append(
        app.element("span", "news-thumb-time", relativeTime(article.published_at)),
      );
    }
    body.append(meta);
    card.append(body);
    return card;
  }

  function byNewest(left, right) {
    return (right.published_at || "").localeCompare(left.published_at || "");
  }

  let newsData = null;
  try {
    newsData = await app.fetchJson("data/news.json", { optional: true });
  } catch (error) {
    app.logDataError(error);
  }
  const articles =
    newsData && Array.isArray(newsData.articles) ? newsData.articles : [];

  /* --- トップページ: 最新記事6件のサムネダイジェスト --------------------------- */
  const digest = document.querySelector("#news-digest");
  if (digest) {
    const latest = articles.slice().sort(byNewest).slice(0, 6);
    if (latest.length > 0) {
      digest.classList.remove("news-grid");
      digest.classList.add("news-thumb-grid");
      digest.replaceChildren(...latest.map(createArticleCard));
    } else {
      // 記事が取れない場合は従来の最重要ソース6選で成立させる
      const featured = sources.filter((source) => source.priority === 1);
      digest.replaceChildren(
        ...featured.map((source) =>
          createSourceCard(source, CATEGORY_LABELS[source.category] || ""),
        ),
      );
    }
  }

  /* --- ニュースページ: カテゴリタブ + 記事カードグリッド + ソースカード ---------- */
  const tablist = document.querySelector("#news-tabs");
  const feedBox = document.querySelector("#news-feed");
  const cardsBox = document.querySelector("#news-cards");
  if (!tablist || !feedBox || !cardsBox) {
    return;
  }

  function renderFeed(category) {
    const lang = FEED_LANG_BY_CATEGORY[category];
    if (!lang) {
      feedBox.hidden = true;
      feedBox.replaceChildren();
      return;
    }
    const matched = articles.filter((article) => article.lang === lang);
    feedBox.hidden = false;

    const header = app.element("div", "news-feed-header");
    header.append(app.element("h2", "news-feed-title", "最新ニュース"));

    if (matched.length === 0) {
      feedBox.replaceChildren(
        header,
        app.element(
          "p",
          "news-feed-note",
          "最新記事を取得できませんでした。各メディアで最新情報を確認してください。",
        ),
      );
      return;
    }

    if (newsData.generated_at) {
      const updated = new Intl.DateTimeFormat("ja-JP", {
        timeZone: "Asia/Tokyo",
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date(newsData.generated_at));
      header.append(
        app.element(
          "span",
          "news-feed-updated",
          `更新: ${updated} / Google News RSS`,
        ),
      );
    }

    const grid = app.element("div", "news-thumb-grid");
    grid.append(...matched.map((article) => createArticleCard(article)));
    feedBox.replaceChildren(header, grid);
  }

  function renderCards(category) {
    const label = CATEGORY_LABELS[category] || "";
    cardsBox.replaceChildren(
      ...sourcesFor(category).map((source) => createSourceCard(source, label)),
    );
  }

  function selectTab(category) {
    tablist.querySelectorAll(".news-tab").forEach((tab) => {
      const selected = tab.dataset.category === category;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
    });
    renderFeed(category);
    renderCards(category);
  }

  tablist.addEventListener("click", (event) => {
    const tab = event.target.closest(".news-tab");
    if (tab) {
      selectTab(tab.dataset.category);
    }
  });

  selectTab("official");
});
