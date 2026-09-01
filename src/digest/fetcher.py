"""多源采集：RSS 拉取 + 时效过滤 + 双层关键词相关性打分.

2026-08-31 修订（相关性放水事故复盘）：
- 旧版泛化词（launch/review/release）单独命中即可入选，
  导致太空望远镜、棋牌网站等无关内容混入日报；
- 新版双层结构：strong 核心词决定"入选资格"，weak 泛化词只加分；
- 英文关键词按 \\b 词边界整词匹配（避免 mate 命中 climate、soc 命中 social）；
- 摘要先剥离 HTML 标签再进入打分与展示。
"""

from __future__ import annotations

import html as html_mod
import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser

from .config_loader import Article, load_config

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """剥离 HTML 标签与实体，避免 feat-image 之类的标签混进摘要."""
    text = _TAG_RE.sub(" ", text or "")
    return html_mod.unescape(text).strip()


def _kw_hit(word: str, text: str) -> bool:
    """英文词整词匹配，中文词子串匹配."""
    if word.isascii():
        return re.search(rf"\b{re.escape(word)}\b", text) is not None
    return word in text


def _parse_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        st = getattr(entry, key, None)
        if st:
            return datetime(*st[:6], tzinfo=timezone.utc)
    return None


def _score(article: Article, keywords: dict) -> tuple[float, str]:
    """双层打分：strong 命中 >= 1 才有资格；weak 只加分.

    score = 来源权威度*0.5 + strong命中数*3 + weak命中数*0.5
    """
    strong: dict[str, list[str]] = keywords.get("strong", {})
    weak: list[str] = keywords.get("weak", [])
    negative: list[str] = keywords.get("negative", [])
    text = f"{article.title} {article.summary}".lower()

    # 黑名单一票否决（如望远镜/棋牌/彩票类噪声）
    if any(_kw_hit(w, text) for w in negative):
        return 0.0, ""

    weak_hits = sum(1 for w in weak if _kw_hit(w, text))
    best_score, best_cat = 0.0, ""
    for cat, words in strong.items():
        hits = sum(1 for w in words if _kw_hit(w, text))
        if hits == 0:
            continue  # 该主线核心词零命中 → 本条不因泛化词入选
        score = article.source_priority * 0.5 + hits * 3 + weak_hits * 0.5
        if score > best_score:
            best_score, best_cat = score, cat
    return best_score, best_cat


def fetch_all(max_age_hours: int = 36) -> list[Article]:
    """拉取全部信源，过滤时效，打分并丢弃零分条目."""
    cfg = load_config()
    keywords: dict = cfg["keywords"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    articles: list[Article] = []

    for src in cfg["sources"]:
        name = src["name"]
        try:
            parsed = feedparser.parse(
                src["url"], request_headers={"User-Agent": UA}
            )
            if parsed.bozo and not parsed.entries:
                log.warning("feed %s 解析失败: %s", name, parsed.bozo_exception)
                continue
        except Exception as exc:  # noqa: BLE001 单源失败不拖垮全局
            log.warning("feed %s 拉取异常: %s", name, exc)
            continue

        for entry in parsed.entries:
            published = _parse_time(entry)
            if published and published < cutoff:
                continue
            art = Article(
                title=entry.get("title", "").strip(),
                url=entry.get("link", ""),
                source=name,
                source_priority=int(src.get("priority", 5)),
                published=published,
                summary=_strip_html(entry.get("summary", ""))[:400],
            )
            if not art.title or not art.url:
                continue
            art.score, art.category = _score(art, keywords)
            if art.score > 0:
                articles.append(art)

    log.info("采集完成: %d 条进入候选池", len(articles))
    return articles
