"""HTML 邮件渲染：V3-Refined 版式（暖纸底 · 单一朱砂强调色 · 发丝线分隔）.

设计规范（反"AI 感"约束）：
- 单一去饱和强调色 #A85638（朱砂），全篇仅此一色
- 无纯黑：正文墨色 #211E1B，辅助 #5C5850 / #8B857C
- 无圆角卡片阵列：条目之间用 1px 发丝线分隔，分组靠留白与字重
- 层级由字重、字距、留白控制，不靠大字号
- 链接为下划线文字，不做彩色按钮
"""

from __future__ import annotations

import html

from .config_loader import Digest

# 栏目中文 -> 英文小标签（未命中的栏目不显示英文标签）
SECTION_EN = {
    "今日速览": "BRIEF",
    "新形态智能硬件": "NOVEL FORM",
    "国内 · 新品发布与规格拆解": "PRODUCTS · CN",
    "国外 · 新品发布与规格拆解": "PRODUCTS · GLOBAL",
    "新品发布与规格拆解": "PRODUCTS",       # 旧版栏目名（历史存档兼容）
    "技术与芯片动向": "SILICON",
    "融资与招聘信号": "CAPITAL",
    "一句话点评": "COMMENT",
    "AI 眼镜与可穿戴": "WEARABLES",
    "AI 耳机与挂件": "COMPANIONS",
    "新 AI 产品与消费电子": "NEW PRODUCTS",
    "重大发布与融资动态": "CAPITAL",
    "端侧芯片与 SoC": "SILICON",
}

# 章节序号在 render() 中按栏目出现顺序自动生成（01, 02, ...）。
# 不用静态映射表的原因：栏目会随需求增减（2026-09-01 拆国内/国外，
# 2026-09-04 新增「新形态智能硬件」），静态表会让历史存档在重新渲染时
# 编号错位；按序编号对任何时代的存档都自洽，栏目增减零维护。

ACCENT = "#A85638"
INK = "#211E1B"
BODY = "#5C5850"
MUTED = "#8B857C"
FAINT = "#B5AFA5"
HAIRLINE = "#E8E4DD"
PAPER = "#F5F4F0"

CSS = f"""
body{{margin:0;padding:32px 16px;background:{PAPER};}}
.wrap{{max-width:600px;margin:0 auto;background:#FFFFFF;border:1px solid {HAIRLINE};}}
.inner{{padding:40px 44px 36px;}}
.mast{{border-bottom:2px solid {INK};padding-bottom:20px;margin-bottom:8px;}}
.mast .kicker{{font-size:11px;letter-spacing:.32em;color:{ACCENT};font-weight:600;margin-bottom:10px;
  font-family:ui-monospace,'SF Mono',Menlo,monospace;}}
.mast h1{{font-size:22px;font-weight:700;letter-spacing:.02em;color:{INK};margin:0 0 8px;
  font-family:-apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;}}
.mast .date{{font-size:12px;color:{MUTED};letter-spacing:.08em;}}
.mast .date b{{color:{INK};font-weight:500;}}
.ov{{padding:20px 0 22px;border-bottom:1px solid {HAIRLINE};}}
.ov .ov-t{{font-size:11px;letter-spacing:.28em;color:{MUTED};margin-bottom:14px;}}
.ov-row{{padding:7px 0;font-size:13.5px;line-height:1.75;color:#3D3A35;}}
.ov-row .m{{font-family:ui-monospace,'SF Mono',Menlo,monospace;font-size:11px;color:{ACCENT};margin-right:14px;}}
.sec{{padding:30px 0 14px;border-bottom:1px solid {INK};}}
.sec .idx{{font-family:ui-monospace,'SF Mono',Menlo,monospace;font-size:12px;color:{ACCENT};margin-right:12px;}}
.sec .name{{font-size:15px;font-weight:600;color:{INK};letter-spacing:.04em;}}
.sec .en{{font-size:10px;letter-spacing:.24em;color:{FAINT};margin-left:12px;}}
.item{{padding:20px 0;border-bottom:1px solid {HAIRLINE};}}
.item:last-child{{border-bottom:none;}}
.item .no{{font-family:ui-monospace,'SF Mono',Menlo,monospace;font-size:11px;color:{FAINT};margin-bottom:8px;}}
.item .t{{font-size:14.5px;font-weight:600;color:{INK};line-height:1.55;margin-bottom:6px;}}
.rg{{font-size:11px;font-weight:400;color:{ACCENT};margin-right:6px;letter-spacing:.02em;}}
.item .s{{font-size:13px;line-height:1.8;color:{BODY};margin-bottom:10px;}}
.item .meta{{font-size:11.5px;color:{MUTED};letter-spacing:.03em;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;}}
.item .meta a{{color:{ACCENT};text-decoration:none;border-bottom:1px solid #D8B7A5;padding-bottom:1px;}}
.cm{{padding:18px 0;border-bottom:1px solid {HAIRLINE};}}
.cm:last-child{{border-bottom:none;}}
.cm .no{{font-family:ui-monospace,'SF Mono',Menlo,monospace;font-size:11px;color:{FAINT};margin-bottom:6px;}}
.cm .s{{font-size:13.5px;line-height:1.85;color:#3D3A35;}}
.foot{{margin-top:8px;border-top:2px solid {INK};padding-top:18px;font-size:11px;line-height:1.9;color:{MUTED};}}
.foot .stat{{margin-bottom:10px;font-family:ui-monospace,'SF Mono',Menlo,monospace;font-size:10.5px;color:{FAINT};letter-spacing:.05em;}}
@media only screen and (max-width:520px){{
  .inner{{padding:28px 22px 24px;}}
  body{{padding:16px 8px;}}
}}
"""


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def render(digest: Digest, issue_no: str = "") -> str:
    """渲染完整日报 HTML.

    issue_no: 期号（可选），如 "No.001"，为空则不显示。
    """
    issue = f"&ensp;·&ensp;{html.escape(issue_no)}" if issue_no else ""
    parts = [
        f"<div class='mast'><div class='kicker'>AI HARDWARE DIGEST</div>"
        f"<h1>AI 硬件情报日报</h1>"
        f"<div class='date'><b>{_esc(digest.date)}</b>{issue}</div></div>"
    ]

    # 今日速览
    if digest.overview:
        rows = "".join(
            f"<div class='ov-row'><span class='m'>{i:02d}</span>{_esc(o)}</div>"
            for i, o in enumerate(digest.overview, 1)
        )
        parts.append(f"<div class='ov'><div class='ov-t'>今日速览&ensp;/&ensp;BRIEF</div>{rows}</div>")

    # 正文章节：序号按栏目出现顺序自动生成
    no = 0
    sec_no = 0
    for sec in digest.sections:
        items = sec.get("items", [])
        if not items:
            continue
        sec_no += 1
        en = SECTION_EN.get(sec["name"], "")
        en_html = f"<span class='en'>{html.escape(en)}</span>" if en else ""
        parts.append(
            f"<div class='sec'><span class='idx'>{sec_no:02d}</span>"
            f"<span class='name'>{_esc(sec['name'])}</span>{en_html}</div>"
        )
        for it in items:
            no += 1
            region = getattr(it, "region", "")
            rg = f"<span class='rg'>[{_esc(region)}]</span>" if region else ""
            comment = f"<div class='s' style='margin-top:8px;color:#3D3A35'>{_esc(it.comment)}</div>" if it.comment else ""
            src = getattr(it, "source", "")
            left = f"{_esc(src)}" if src else "&nbsp;"
            parts.append(
                f"<div class='item'><div class='no'>{no:02d}</div>"
                f"<div class='t'>{rg}{_esc(it.title)}</div>"
                f"<div class='s'>{_esc(it.summary)}</div>"
                f"{comment}"
                f"<div class='meta'><span>{left}</span>"
                f"<a href='{html.escape(it.link, quote=True)}'>查看来源 →</a></div>"
                f"</div>"
            )
    parts.append(
        "<div class='foot'><div class='stat'>AUTOMATED PIPELINE&ensp;/&ensp;ALL SOURCES LINKED</div>"
        "本邮件由个人 Agent 流水线自动生成，全部条目附溯源链接。<br>"
        "回复编号即可反馈（如「2、5 有用，3 没用」），Agent 将据此调整信源权重。</div>"
    )

    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>AI 硬件情报日报 {html.escape(digest.date)}</title>"
        f"<style>{CSS}</style></head><body><div class='wrap'><div class='inner'>"
        + "".join(parts)
        + "</div></div></body></html>"
    )
