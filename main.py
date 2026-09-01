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
    parser.add_argument("--limit", type=int, default=30, help="进入 LLM 摘要的候选条数")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run(dry_run=args.dry_run, limit=args.limit)
    print(f"完成: {result}")
