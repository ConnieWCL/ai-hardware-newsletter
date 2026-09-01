# AI Hardware Digest — 多源 AI 硬件情报日报 Agent

个人侧项目：自动追踪国际智能硬件 / AI 硬件 / AI 产品动态，每天 08:30 生成一份 5 分钟读完、全条目可溯源的结构化邮件日报。

**公开存档**：https://conniewcl.github.io/ai-hardware-newsletter/　·　**产品文档**：[docs/PRD.md](docs/PRD.md)

## 架构

```
RSS 信源 (12 源, 中英文)          质量闸门
        │                          │
        ▼                          ▼
   fetcher.py  ──时效过滤──►  deduper.py  ──URL 规范化 + Shingle/Jaccard 聚类──►  summarizer.py
   (feedparser, 关键词打分)        (两级去重)                                    (LLM 结构化摘要, JSON Schema)
                                                                                │
        ┌───────────────────────────────────────────────────────────────────────┘
        ▼
   renderer.py ──► sender.py (SMTP) ──► 每日邮件
        │
        ▼
   data/archive/*.json (全量存档, 周报/信源健康度分析的数据底座)
        │
        ▼
   scripts/build_site.py ──► 静态存档站 ──► gh-pages 分支 ──► GitHub Pages 公开访问
```

核心设计决策见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env   # 填入 LLM_API_KEY 和 163 邮箱授权码
python main.py --dry-run   # 本地试跑，产物在 out/，不发送
python tests/test_deduper.py  # 单元测试
```

## 部署（GitHub Actions，零服务器）

1. 推送到 GitHub 私有仓库
2. 在仓库 Settings → Secrets 配置 `LLM_API_KEY` / `SMTP_USER` / `SMTP_PASS` / `DIGEST_TO`
3. 完成。每天 UTC 00:30（北京 08:30）自动执行，存档自动回提交；Actions 页可手动触发调试

## 配置即调优

- `config/sources.yaml` — 信源清单与权威度。原则：**连续 3 天产出为零的源移除**（依据 data/archive 数据）
- `config/keywords.yaml` — 五条主线命中词：AI 眼镜可穿戴 / AI 耳机挂件 / 新 AI 产品与消费电子 / 发布与融资 / 端侧芯片 SoC
- `config/config.yaml` — LLM、条目上限、时效窗口、SMTP

## 质量红线

| 红线 | 机制 |
|---|---|
| 不重复 | 两级去重：URL 规范化 + 标题 Shingle/Jaccard 聚类 (阈值 0.6) |
| 不杜撰 | LLM 只基于给定材料产出；渲染前校验 link 必须来自输入集合，否则丢弃 |
| 不超载 | 每日 ≤12 条，800-1200 字；LLM 指令明确"宁缺毋滥" |
| 不缺席 | LLM 失败降级为标题列表；发送失败 HTML 落盘 out/；单源失败跳过不阻塞 |

## 成本

- 计算：GitHub Actions 免费额度（公开仓库无限/私有 2000 分钟/月，单次 <3 分钟）
- LLM：日均约 1 万 token 输入 + 2 千输出 ≈ ¥0.02-0.05/天（DeepSeek 价格）
- 存储：无

## Roadmap

- [ ] 每封邮件末尾收集编号反馈，周度自动调整关键词权重（反馈闭环）
- [ ] 周报生成：基于 data/archive 聚合周度趋势综述
- [ ] 信源健康度看板：各源 7 天产出条数与被采纳率
