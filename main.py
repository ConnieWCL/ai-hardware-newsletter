"""CLI 入口：python main.py [--dry-run] [--limit N]."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from digest.pipeline import run  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI 硬件情报日报")
    parser.add_argument("--dry-run", action="store_true", help="只生成不发送，产物落在 out/")
    parser.add_argument("--limit", type=int, default=100,
                        help="进入选材配额的候选池上限（送入 LLM 的 22 条材料由配额函数从中选出）")
    parser.add_argument("--force", action="store_true",
                        help="跳过幂等守卫，当日已发过也强制重跑（人工补发用）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run(dry_run=args.dry_run, limit=args.limit, force=args.force)
    print(f"完成: {result}")
