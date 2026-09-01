"""LLM 结构化摘要：只准基于给定材料产出 JSON，每条强制携带来源链接.

幻觉控制策略（面试常问点）：
1. 输入只给已打分、已去重的候选条目（标题+摘要+URL），不给自由发挥空间；
2. 输出强约束为 JSON Schema，link 字段必须原样回填输入中的 URL，
   渲染层校验 link 是否出现在输入集合中，不在则丢弃该条；
3. temperature=0.2 + "信息不足时宁缺毋滥"的显式指令；
4. API 失败指数退避重试 3 次，最终失败则整期日报降级为"仅标题列表"。
"""

from __future__ import annotations

import json
import logging
import re
import time

import httpx

from . import budget
from .config_loader import EN_SOURCES, Digest, DigestItem, env, load_config
from .deduper import jaccard, shingles

log = logging.getLogger(__name__)

PROMPT = """你是 AI 硬件领域的产品分析师，为一位前旗舰手机产品经理（正在求职国内 AI 硬件方向）撰写每日情报日报。

材料（已去重，每条含标题/摘要/来源链接，中英文混合，已按相关性排序）：
{materials}

要求：
1. 只使用材料中的信息，不得编造；每条 item 的 link 必须原样复制材料中的 URL；
2. 按以下六个栏目组织：今日速览 / 国内 · 新品发布与规格拆解 / 国外 · 新品发布与规格拆解 / 技术与芯片动向 / 融资与招聘信号 / 一句话点评；
3. 每条 item 必须带 region 字段："国内"或"国外"。判定规则：按新闻主体公司的注册地；跨国合作按主导方；中国公司出海（如 Rokid 进军欧洲）算国内；外国公司在华动态（如苹果国行定价）算国外；
4. 今日速览的每句话以 [国内] 或 [国外] 开头；
5. 总条目不超过 {max_items} 条，国外条目（region="国外"）不少于 5 条——英文源（the-verge / techcrunch / arstechnica / 9to5google / engadget 等）的新闻是国外板块的主要材料，不得因国内新闻多而全部挤掉；若英文材料确实不足，能收几条收几条，不得编造；
6. 国内动态优先：华为、小米、OPPO、vivo、荣耀等中国厂商及供应链的重大发布置于速览首位；技术与芯片、融资与招聘栏目内国内条目在前、国外条目在后；
7. 新品条目尽量点出定价、定位、差异化卖点或成本/功耗取舍；
8. 融资条目点出"谁拿钱=谁扩招"的求职信号；
9. 全文以简体中文输出：英文材料的标题和内容必须翻译为中文，专有名词（如 Snapdragon、NPU）可保留英文缩写；
10. 材料条目已按相关性得分排序：优先保留编号靠前的条目，不要用它认为"有趣"但得分靠后的条目挤掉高相关性新闻；
11. 同一条新闻只能出现在一个栏目里，严禁跨栏目重复；同一产品的多条报道请合并为一条；
12. 没有足够分量的新闻就删栏目，绝不凑数。

只输出 JSON，格式：
{{"overview": ["[国内] 一句话要点", ...],
  "sections": [{{"name": "栏目名", "items": [{{"title": "...", "summary": "80字以内", "link": "原样URL", "region": "国内或国外", "comment": "可选点评"}}]}}]}}"""


MAX_MATERIALS = 22       # 送进 LLM 的候选上限：压输入 token，避免撞免费层 TPM 限流
SUMMARY_CHARS = 120      # 每条摘要的送入长度上限
EN_QUOTA = 0.4           # 材料配额：英文源条目至少占 40%，防止国内新闻挤掉国外板块原料


def _balance_regions(reps: list) -> list:
    """保证送入 LLM 的材料里英文源（国外原料）不低于配额.

    中文源条目得分普遍更高（信源 priority + 关键词命中密度），纯按得分截断
    会导致材料几乎全为国内新闻，LLM 再想输出国外板块也无米下锅——
    国外占比问题的根因在选材层，不在提示词层。
    """
    en = [a for a in reps if a.source in EN_SOURCES]
    cn = [a for a in reps if a.source not in EN_SOURCES]
    # 英文保底：至少 40% 的材料槽位（材料不足时能占多少占多少）
    min_en = min(len(en), round(MAX_MATERIALS * EN_QUOTA))
    # 剩余槽位给中文；中文不足时槽位回补给英文
    cn_slots = MAX_MATERIALS - min_en
    cn_pick = cn[:cn_slots]
    en_slots = MAX_MATERIALS - len(cn_pick)
    en_pick = en[:en_slots]
    # 中文在前（保持国内优先的排序惯性），英文紧随其后
    return cn_pick + en_pick


def _build_materials(reps: list) -> str:
    lines = []
    for i, a in enumerate(reps[:MAX_MATERIALS], 1):
        lines.append(f"[{i}] {a.title} | 来源:{a.source} | {a.url}\n    {a.summary[:SUMMARY_CHARS]}")
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """从模型输出中鲁棒地抽取 JSON（容忍 markdown 代码块包裹）."""
    # 推理模型（如 gpt-oss）可能在 JSON 前后附带思考过程，先剥离代码块围栏
    cleaned = re.sub(r"```(?:json)?", "", text or "")
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        snippet = (text or "")[:200].replace("\n", " ")
        raise ValueError(f"模型输出中未找到 JSON（前 200 字符：{snippet}）")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        # 输出被 max_output_tokens 截断：给出可诊断的报错
        raise ValueError(f"JSON 解析失败（疑似输出被截断）: {exc}") from exc


def summarize(reps: list, max_items: int = 16) -> Digest:
    cfg = load_config()
    llm = cfg["llm"]
    api_key = env("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 LLM_API_KEY 环境变量")
    # 提供商可整体通过环境变量切换（OpenAI 兼容接口：Groq / OpenRouter / DeepSeek…），
    # 未设置时回落到 config.yaml 的默认值
    base_url = env("LLM_BASE_URL") or llm["base_url"]
    model = env("LLM_MODEL") or llm["model"]

    # 预算闸门：月度 token 用量将超阈值时主动放弃 LLM，走降级路径（不重试、不产生费用）
    # 选材前先做地域配额平衡，防止国内新闻挤掉国外板块原料
    balanced = _balance_regions(reps)
    prompt_text = PROMPT.format(materials=_build_materials(balanced), max_items=max_items)
    monthly_cap = int(cfg.get("budget", {}).get("monthly_tokens", 500_000))
    budget.check(monthly_cap, budget.estimate_input_tokens(prompt_text) + llm.get("max_output_tokens", 2000))

    payload = {
        "model": model,
        "temperature": llm.get("temperature", 0.2),
        "max_tokens": int(llm.get("max_output_tokens", 4000)),
        "messages": [
            {"role": "user",
             "content": prompt_text},
        ],
        # 要求模型直接产出 JSON 对象（OpenAI 兼容接口通用字段）
        "response_format": {"type": "json_object"},
    }
    # 推理模型（gpt-oss 系列）默认会把 token 大量消耗在思考过程，导致 JSON 被
    # max_tokens 截断。显式压低推理强度；非推理型提供商不支持该字段则不加。
    if "gpt-oss" in model:
        payload["reasoning_effort"] = llm.get("reasoning_effort", "low")

    last_exc: Exception | None = None
    for attempt in range(3):
        resp = None
        try:
            resp = httpx.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload, timeout=90,
            )
            resp.raise_for_status()
            body = resp.json()
            # 记账：优先使用 API 返回的真实 usage，缺失时回退为估算值
            u = body.get("usage") or {}
            budget.record(int(u.get("total_tokens", 0)) or budget.estimate_input_tokens(prompt_text))
            data = _extract_json(body["choices"][0]["message"]["content"])
            return _validate(data, balanced, max_items)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("LLM 调用第 %d 次失败: %s", attempt + 1, exc)
            # 429 限流：优先遵循服务端 Retry-After，否则用更长的退避
            # （免费层 TPM 限制下，2s/4s 的短退避必然连续撞墙）
            wait = _retry_wait(resp, attempt)
            if attempt < 2:
                time.sleep(wait)
                log.info("等待 %s 秒后重试", wait)
    raise RuntimeError(f"LLM 调用重试耗尽: {last_exc}")


def _retry_wait(resp, attempt: int) -> float:
    """退避时长：优先 Retry-After 响应头，否则 20s / 45s."""
    if resp is not None:
        ra = getattr(resp, "headers", {}).get("retry-after")
        if ra:
            try:
                return min(float(ra), 60.0)
            except ValueError:
                pass
    return [20.0, 45.0][min(attempt, 1)]


def _validate(data: dict, reps: list, max_items: int = 16) -> Digest:
    """校验：link 必须来自输入材料（防幻觉），并合并跨栏目重复条目.

    模型偶尔会把同一条新闻放进两个栏目（如"新品发布"与"规格拆解"各一次），
    这里用 link 精确去重 + 标题相似度去重做最后一道收口。
    """
    valid_links = {r.url for r in reps}
    link_source = {r.url: r.source for r in reps}
    digest = Digest(date=time.strftime("%Y-%m-%d"))
    digest.overview = [str(x) for x in data.get("overview", [])][:4]
    total = 0
    seen_links: set[str] = set()
    seen_titles: list[set[str]] = []
    for sec in data.get("sections", []):
        items = []
        for it in sec.get("items", []):
            if total >= max_items:
                break
            link = it.get("link")
            if link not in valid_links:
                log.warning("丢弃无法溯源条目: %s", it.get("title"))
                continue
            if link in seen_links:
                log.info("丢弃跨栏目重复条目: %s", it.get("title"))
                continue
            sh = shingles(str(it.get("title", "")))
            if any(jaccard(sh, t) >= 0.6 for t in seen_titles):
                log.info("丢弃标题重复条目: %s", it.get("title"))
                continue
            seen_links.add(link)
            seen_titles.append(sh)
            items.append(DigestItem(
                title=str(it.get("title", ""))[:80],
                summary=str(it.get("summary", ""))[:200],
                link=it["link"],
                comment=str(it.get("comment", ""))[:120],
                source=link_source.get(it["link"], ""),   # 回填来源名，供邮件元信息行展示
                region=str(it.get("region", ""))[:4] or "",  # 国内/国外标注，供版式渲染
            ))
            total += 1
        if items:
            digest.sections.append({"name": sec.get("name", ""), "items": items})
    return digest
