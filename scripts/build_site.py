"""把 data/archive/*.json 构建成可发布的静态存档站（输出到 site/）.

设计取舍：
- 每期页面直接复用邮件渲染器 renderer.render()，保证网页与邮件版式完全一致，
  不引入第二套模板（避免"邮件好看、网页走形"的维护负担）；
- 索引页手写，承载项目说明与统计，这个页面是给访客（面试官）看的第一屏；
- 输出纯静态 HTML + 内联样式，零构建工具、零依赖，GitHub Pages 直接托管。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from digest.config_loader import Digest, DigestItem  # noqa: E402
from digest.renderer import render  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIR = ROOT / "data" / "archive"    # 日报存档（GitHub Actions 流水线）
SITE_DIR = ROOT / "site"
DIGEST_DIR = SITE_DIR / "digest"

REPO_URL = "https://github.com/ConnieWCL/ai-hardware-newsletter"

# 自定义域名：GitHub Pages 读取发布分支根目录的 CNAME 文件自动绑定。
# 必须由 build 生成（而非手工放置），因为部署脚本每次 orphan 全量重建 gh-pages。
# 命名规范（2026-09-04 用户定）：所有地方统一 "aihardwarenewsletter"，不带连字符/下划线
# 腾讯云 DNS 需配 CNAME 记录：aihardwarenewsletter -> conniewcl.github.io
CUSTOM_DOMAIN = "aihardwarenewsletter.hiconnie.com"

CSS = """
*{box-sizing:border-box;}
body{margin:0;padding:32px 16px 64px;background:#F5F4F0;color:#3D3A35;
  font-family:-apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;
  -webkit-font-smoothing:antialiased;}
.wrap{max-width:640px;margin:0 auto;background:#FFFFFF;border:1px solid #E8E4DD;}
.inner{padding:40px 44px 36px;}
.mast{border-bottom:2px solid #211E1B;padding-bottom:20px;margin-bottom:22px;}
.kicker{font-size:11px;letter-spacing:.32em;color:#A85638;font-weight:600;margin-bottom:10px;
  font-family:ui-monospace,'SF Mono',Menlo,monospace;}
h1{font-size:23px;font-weight:700;letter-spacing:.02em;color:#211E1B;margin:0 0 8px;}
.sub{font-size:12.5px;color:#8B857C;letter-spacing:.04em;}
/* 流水线流程条：描边芯片 + 等宽编号，传达"机器执行"的过程感 */
.pipe{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:0 0 26px;}
.step{font-size:11.5px;color:#211E1B;border:1px solid #E8E4DD;padding:6px 11px;white-space:nowrap;
  font-family:ui-monospace,'SF Mono',Menlo,monospace;letter-spacing:.02em;}
.step i{font-style:normal;color:#A85638;font-size:10px;margin-right:7px;}
.step em{font-style:normal;color:#A85638;}
.pipe .arr{color:#C9C4BB;font-size:11px;}
/* 亮点清单：朱砂短横线标记 + 粗体引导词；正文灰、关键数字朱砂等宽 */
.hl{list-style:none;margin:0 0 28px;padding:0;}
.hl li{position:relative;padding-left:18px;margin-bottom:11px;
  font-size:12.5px;line-height:1.75;color:#5C5850;}
.hl li:last-child{margin-bottom:0;}
.hl li::before{content:"";position:absolute;left:0;top:10px;width:8px;height:1px;background:#A85638;}
.hl b{color:#211E1B;font-weight:600;font-size:13px;}
.hl em{font-style:normal;color:#A85638;
  font-family:ui-monospace,'SF Mono',Menlo,monospace;font-size:12px;}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 26px;}
.stat{flex:1;min-width:120px;border:1px solid #E8E4DD;padding:14px 16px;}
.stat .n{font-size:20px;font-weight:700;color:#211E1B;font-family:ui-monospace,'SF Mono',Menlo,monospace;}
.stat .l{font-size:11px;color:#8B857C;letter-spacing:.06em;margin-top:6px;}
.sec-t{font-size:11px;letter-spacing:.28em;color:#8B857C;margin:0 0 14px;}
.latest{display:block;border:1px solid #211E1B;padding:20px 22px;text-decoration:none;margin-bottom:10px;}
.latest:hover{background:#FAF9F6;}
.latest .d{font-size:11px;letter-spacing:.14em;color:#A85638;
  font-family:ui-monospace,'SF Mono',Menlo,monospace;margin-bottom:8px;}
.latest .t{font-size:15px;font-weight:600;color:#211E1B;line-height:1.6;margin-bottom:8px;}
.latest .m{font-size:12px;color:#8B857C;}
.row{display:flex;justify-content:space-between;align-items:center;gap:12px;
  padding:15px 0;border-bottom:1px solid #E8E4DD;text-decoration:none;flex-wrap:wrap;}
.row:hover .rd{color:#A85638;}
.row:last-child{border-bottom:none;}
.rd{font-size:13.5px;color:#211E1B;font-family:ui-monospace,'SF Mono',Menlo,monospace;letter-spacing:.03em;}
.rm{font-size:11.5px;color:#8B857C;}
.tag{display:inline-block;font-size:10px;letter-spacing:.1em;padding:2px 7px;border:1px solid #D8D4CB;color:#8B857C;}
.tag.llm{border-color:#D8B7A5;color:#A85638;}
.foot{margin-top:26px;border-top:2px solid #211E1B;padding-top:18px;
  font-size:11.5px;line-height:1.9;color:#8B857C;}
.foot a{color:#A85638;text-decoration:none;border-bottom:1px solid #D8B7A5;}
@media only screen and (max-width:520px){
  .inner{padding:28px 22px 24px;}
  body{padding:16px 8px 40px;}
}
"""

BACK_NAV = (
    '<div style="max-width:600px;margin:0 auto;padding:0 0 12px;font-size:12px;">'
    '<a href="../index.html" style="color:#A85638;text-decoration:none;'
    'font-family:ui-monospace,\'SF Mono\',Menlo,monospace;letter-spacing:.04em;">'
    '← 返回存档目录</a></div>'
)


def _digest_from_json(data: dict) -> Digest:
    """从存档 JSON 还原 Digest；兼容只有扁平 items 的旧存档."""
    sections = data.get("sections") or []
    if not sections and data.get("items"):
        sections = [{"name": "今日情报", "items": data["items"]}]
    return Digest(
        date=data.get("date", ""),
        overview=data.get("overview", []),
        sections=[
            {
                "name": s.get("name", ""),
                "items": [
                    DigestItem(
                        title=i.get("title", ""),
                        summary=i.get("summary", ""),
                        link=i.get("link", ""),
                        comment=i.get("comment", ""),
                        source=i.get("source", ""),
                        region=i.get("region", ""),
                    )
                    for i in s.get("items", [])
                ],
            }
            for s in sections
        ],
    )


def _fmt_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str
    return f"{d.year} 年 {d.month} 月 {d.day} 日"


def _index_html(entries: list[dict], stats: dict) -> str:
    rows = []
    for e in entries:
        mode_tag = ('<span class="tag llm">完整版</span>' if e["mode"] == "llm"
                    else '<span class="tag">速览版</span>')
        rows.append(
            f'<a class="row" href="digest/{e["date"]}.html">'
            f'<span class="rd">{_fmt_date(e["date"])}　{e["issue"]}</span>'
            f'<span class="rm">{e["count"]} 条　{mode_tag}</span>'
            f"</a>"
        )

    latest = entries[0]
    latest_titles = "、".join(t["title"][:22] for t in latest["items"][:3])

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 硬件情报日报 · 公开存档</title>
<meta name="description" content="每日 AI 硬件 / 智能硬件情报日报的公开存档，由个人 Agent 流水线自动生成。">
<style>{CSS}</style></head><body><div class="wrap"><div class="inner">

<div class="mast">
  <div class="kicker">AI HARDWARE DIGEST</div>
  <h1>AI 硬件情报日报 · 公开存档</h1>
  <div class="sub">每日上午 10 点自动生成　·　国内动态优先　·　全部条目附溯源链接</div>
</div>

<div class="sec-t">全自动流水线&ensp;/&ensp;PIPELINE</div>
<div class="pipe">
  <span class="step"><i>01</i>采集 <em>16</em> 中英信源</span><span class="arr">→</span>
  <span class="step"><i>02</i>双层关键词过滤</span><span class="arr">→</span>
  <span class="step"><i>03</i>两级去重</span><span class="arr">→</span>
  <span class="step"><i>04</i>双配额选材</span><span class="arr">→</span>
  <span class="step"><i>05</i>LLM 结构化摘要</span><span class="arr">→</span>
  <span class="step"><i>06</i>自动发信 + 发布</span>
</div>

<div class="sec-t">设计亮点&ensp;/&ensp;HIGHLIGHTS</div>
<ul class="hl">
  <li><b>规则与 LLM 严格分工</b>——采集、去重、事实校验交给确定性规则，LLM 只负责判断与表达；每条摘要强制附溯源链接，杜绝幻觉。</li>
  <li><b>三层关键词过滤</b>——strong 定入选资格、weak 只加分、negative 一票否决，防止泛化词把无关新闻带进日报。</li>
  <li><b>两级去重</b>——URL 规范化精确匹配 + Shingle-Jaccard 标题聚类，同一事件只报一次。</li>
  <li><b>地域 × 品类双配额</b>——国外条目 <em>≥30%</em>、新形态硬件 <em>≥36%</em> 联合选择，AR/VR 眼镜、智能戒指等低声量品类不被手机 / PC 大众声量淹没。</li>
  <li><b>七栏结构化输出</b>——新形态硬件置顶、国内外新品分栏；每日 <em>≤16</em> 条、5–7 分钟读完，宁缺毋滥。</li>
  <li><b>全链路零成本 + 三层降级</b>——GitHub Actions 调度 + Groq 免费层 + Pages 托管，日均成本 <em>¥0</em>；LLM 不可用时自动降级为规则速览版，日报不缺席。</li>
</ul>

<div class="stats">
  <div class="stat"><div class="n">{stats["days"]}</div><div class="l">累计期数</div></div>
  <div class="stat"><div class="n">{stats["items"]}</div><div class="l">累计情报条目</div></div>
  <div class="stat"><div class="n">¥0</div><div class="l">日均成本</div></div>
</div>

<div class="sec-t">最新一期&ensp;/&ensp;LATEST</div>
<a class="latest" href="digest/{latest["date"]}.html">
  <div class="d">{_fmt_date(latest["date"])}　{latest["issue"]}</div>
  <div class="t">{latest_titles}{"…" if len(latest["items"]) > 3 else ""}</div>
  <div class="m">共 {latest["count"]} 条　·　点击查看完整日报 →</div>
</a>

<div class="sec-t" style="margin-top:30px;">历史存档&ensp;/&ensp;ARCHIVE</div>
{chr(10).join(rows)}

<div class="foot">
本存档由个人 Agent 流水线自动生成，所有条目均附溯源链接，未作人工编辑。<br>
技术实现、架构决策与局限说明见 <a href="{REPO_URL}">GitHub 仓库</a>。
</div>

</div></div></body></html>"""


def build() -> dict:
    # 扫描存档目录（历史遗留的 plan_a 存档一律不展示）
    if not ARCHIVE_DIR.exists():
        raise SystemExit("存档目录不存在")
    files = sorted(ARCHIVE_DIR.glob("*.json"))
    if not files:
        raise SystemExit("存档目录为空，无内容可构建")

    DIGEST_DIR.mkdir(parents=True, exist_ok=True)

    # 先载入并过滤空档（调试运行可能产出零条目存档），再编排期号：
    # 最早一期为 No.001，最新一期号最大
    loaded: list[dict] = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data.get("items"):
            continue
        data["_date"] = data.get("date") or path.stem
        loaded.append(data)
    loaded.sort(key=lambda d: d["_date"])

    entries: list[dict] = []
    for idx, data in enumerate(loaded, 1):
        date_str = data["_date"]
        issue_no = f"No.{idx:03d}"

        digest = _digest_from_json(data)
        page = render(digest, issue_no=issue_no)
        # 注入返回导航（复用邮件模板，不改动渲染器本身）
        page = page.replace("<body>", "<body>" + BACK_NAV, 1)
        (DIGEST_DIR / f"{date_str}.html").write_text(page, encoding="utf-8")

        entries.append({
            "date": date_str,
            "issue": issue_no,
            "mode": data.get("mode", "llm"),
            "count": len(data["items"]),
            "items": data["items"],
        })

    entries.reverse()   # 索引页按日期倒序展示

    stats = {
        "days": len(entries),
        "items": sum(e["count"] for e in entries),
    }
    (SITE_DIR / "index.html").write_text(_index_html(entries, stats), encoding="utf-8")
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    # 自定义域名绑定：GitHub Pages 自动读取该文件并签发 HTTPS 证书
    (SITE_DIR / "CNAME").write_text(CUSTOM_DOMAIN + "\n", encoding="utf-8")

    return {"days": stats["days"], "items": stats["items"], "latest": entries[0]["date"]}


if __name__ == "__main__":
    result = build()
    print(f"构建完成：{result['days']} 期 / {result['items']} 条 / 最新 {result['latest']}")
    print(f"输出目录：{SITE_DIR}")
