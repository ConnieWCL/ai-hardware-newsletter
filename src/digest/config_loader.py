"""数据模型与配置加载."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


@dataclass
class Article:
    """一条原始情报."""

    title: str
    url: str
    source: str            # 来源名，如 the-verge
    source_priority: int   # 来源权威度 1-10
    published: datetime | None = None
    summary: str = ""
    category: str = ""     # 命中的情报主线
    score: float = 0.0     # 相关性得分
    cluster_id: int | None = None

    @property
    def age_hours(self) -> float | None:
        if not self.published:
            return None
        return (datetime.now(timezone.utc) - self.published).total_seconds() / 3600


@dataclass
class DigestItem:
    """日报中的一个条目（LLM 产出的结构化结果）."""

    title: str
    summary: str
    link: str
    comment: str = ""
    source: str = ""       # 来源名（可选），如 "The Verge"
    region: str = ""       # "国内" / "国外"（按新闻主体公司注册地判定）


# 英文信源集合（sources.yaml 的 name）：用于材料配额与降级路径的地域推断
EN_SOURCES = {
    "the-verge", "techcrunch", "arstechnica", "9to5google",
    "engadget", "roadtovr", "uploadvr",
}


@dataclass
class Digest:
    date: str
    sections: list[dict] = field(default_factory=list)  # [{"name":..., "items":[DigestItem]}]
    overview: list[str] = field(default_factory=list)


def load_yaml(path: Path) -> dict | list:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config() -> dict:
    cfg = load_yaml(CONFIG_DIR / "config.yaml")
    sources = load_yaml(CONFIG_DIR / "sources.yaml")
    keywords = load_yaml(CONFIG_DIR / "keywords.yaml")
    cfg["sources"] = sources
    cfg["keywords"] = keywords
    return cfg


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)
