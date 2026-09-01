"""月度用量预算护栏：超过免费额度阈值前主动关闭 LLM，降级为标题列表版日报.

设计动机（面试讲点）：
1. 免费层超额的后果因提供商而异——Groq/Gemini 免费层超额返回 429（不扣费），
   但若未来切到按量计费提供商（DeepSeek 等），超额就是真实账单；
2. 因此把"允许用量"做成显式配置（config.yaml → budget.monthly_tokens），
   运行时先查账再调用：已用量 + 本次预估 > 阈值 → 抛 BudgetExceeded，
   由 pipeline 捕获后走有版式的降级路径，日报不断更；
3. 用量台账持久化在 data/usage.json，按月分桶，可随时人工审计。

预估算法：中文 ~1.6 字/token，保守按 2 字符/token 估算输入，输出按 max_output_tokens 上限计。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

USAGE_FILE = Path(__file__).resolve().parents[2] / "data" / "usage.json"


class BudgetExceeded(RuntimeError):
    """月度 token 预算耗尽，调用方应降级而非重试."""


def _month() -> str:
    return time.strftime("%Y-%m")


def _load_usage() -> dict:
    if USAGE_FILE.exists():
        try:
            return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning("用量台账损坏，已重置")
    return {}


def used_tokens(month: str | None = None) -> int:
    """当月（或指定月）已消耗 token 总量."""
    data = _load_usage()
    return int(data.get(month or _month(), {}).get("tokens", 0))


def check(monthly_cap: int, estimated_tokens: int) -> None:
    """调用 LLM 前的预算闸门：超限即抛 BudgetExceeded."""
    used = used_tokens()
    if used + estimated_tokens > monthly_cap:
        raise BudgetExceeded(
            f"月度预算将超限：已用 {used} + 预估 {estimated_tokens} > 阈值 {monthly_cap}，"
            f"本次跳过 LLM 摘要，降级为标题列表版"
        )


def record(usage_tokens: int, requests: int = 1) -> None:
    """成功调用后记账（usage_tokens 取自 API 响应的 usage 字段，非估算值）."""
    data = _load_usage()
    m = data.setdefault(_month(), {"tokens": 0, "requests": 0})
    m["tokens"] = int(m.get("tokens", 0)) + int(usage_tokens)
    m["requests"] = int(m.get("requests", 0)) + int(requests)
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("记账完成：本月累计 %s tokens / %s 次请求", m["tokens"], m["requests"])


def estimate_input_tokens(text: str) -> int:
    """粗估输入 token 数：按 2 字符/token 保守估计."""
    return len(text) // 2 + 1
