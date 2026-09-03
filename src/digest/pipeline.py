"""流水线编排：采集 -> 去重 -> 摘要 -> 渲染 -> 存档 -> 发送.

降级策略（面试常问点）：
- 单一 RSS 源失败：跳过并记日志，不影响整体；
- LLM 失败：日报降级为"去重后的标题+链接列表"（仍然有用、绝不缺席）；
- 发送失败：HTML 落盘到 out/，人工可补发；历史数据全量存档便于回溯与周报。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from . import fetcher, renderer, summarizer
from .config_loader import ROOT, Digest, DigestItem, load_config
from .deduper import pick_representatives

log = logging.getLogger(__name__)

OUT_DIR = ROOT / "out"
ARCHIVE_DIR = ROOT / "data" / "archive"


def run(dry_run: bool = False, limit: int = 30, force: bool = False) -> dict:
    started = time.time()
    date_str = time.strftime("%Y-%m-%d")
    # 幂等守卫：当日存档已存在（= 邮件已发出过）则跳过本次运行。
    # 背景：workflow 同时配了 repository_dispatch（主通道，方案 A 10:00 后触发）
    # 和 cron（兜底，GitHub 高负载时段定时可延迟数小时），双触发时只有
    # 第一次会真正发信，后续触发只重建存档站，绝不重复发邮件。
    if not dry_run and not force and (ARCHIVE_DIR / f"{date_str}.json").exists():
        log.info("今日存档已存在（%s），跳过本次运行（邮件已发过，避免重复投递）", date_str)
        return {"mode": "skipped", "candidates": 0, "elapsed": round(time.time() - started, 1)}
    cfg = load_config()

    articles = fetcher.fetch_all(max_age_hours=cfg["digest"]["max_age_hours"])
    reps = pick_representatives(articles)[:limit]
    log.info("去重后候选 %d 条，前 %d 条进入选材池（由配额函数选出送入 LLM 的材料）",
             len(pick_representatives(articles)), len(reps))

    mode = "llm"
    subject_suffix = ""
    try:
        digest = summarizer.summarize(reps, max_items=cfg["digest"]["max_items"])
    except Exception as exc:  # noqa: BLE001 降级：LLM 不可用时输出结构化标题速览
        log.error("摘要降级为标题速览: %s", exc)
        items = [
            DigestItem(
                title=a.title,
                summary=(a.summary or "")[:200],
                link=a.url,
                source=a.source,
            )
            for a in reps[: cfg["digest"]["max_items"]]
        ]
        digest = Digest(
            date=time.strftime("%Y-%m-%d"),
            overview=[f"今日共 {len(items)} 条情报。摘要服务暂时不可用，本期为速览版：条目为原始标题与来源摘要，点击「查看来源」可跳转原文。"],
            sections=[{"name": "今日情报速览", "items": items}],
        )
        mode = "fallback"
        subject_suffix = "（速览版）"
    html_body = renderer.render(digest)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"{date_str}.html").write_text(html_body, encoding="utf-8")
    # dry-run 只落 out/ 预览，不写正式存档：
    # 存档是"邮件已发"的幂等信号，也会直接上存档站，测试产物不能污染两者
    if not dry_run:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        # 存档结构保留栏目与速览（公开存档页据此还原完整版式），
        # 同时保留扁平 items 便于脚本统计与回归比对
        (ARCHIVE_DIR / f"{date_str}.json").write_text(
            json.dumps({
                "date": date_str, "mode": mode, "candidates": len(reps),
                "overview": digest.overview if digest else [],
                "sections": [
                    {"name": s["name"], "items": [i.__dict__ for i in s["items"]]}
                    for s in (digest.sections if digest else [])
                ],
                "items": [i.__dict__ for s in (digest.sections if digest else []) for i in s["items"]],
                "elapsed_sec": round(time.time() - started, 1),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if not dry_run:
        from . import sender
        prefix = load_config()["email"]["subject_prefix"]
        subject = f"{prefix} {time.strftime('%Y-%m-%d')}{subject_suffix}"
        sender.send(html_body, subject=subject)

    return {"mode": mode, "candidates": len(reps), "elapsed": round(time.time() - started, 1)}
