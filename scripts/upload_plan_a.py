#!/usr/bin/env python3
"""把方案 A 日报 JSON 上传到 GitHub 仓库 data/plan_a/{date}.json.

用法: python scripts/upload_plan_a.py 2026-09-01
读取 daily_digest/{date}.json，通过 GitHub Contents API 上传到仓库。
PAT 从 .workbuddy/gh_pat.txt 读取（不进仓库）。

设计说明：
- 使用 Contents API（单文件 PUT），而非 Git Data API（多文件合成 commit）。
  方案 A 每日只上传一个 JSON 文件，Contents API 足够且更简单。
- 支持创建（201）和更新（200）：先 GET 获取已有文件 sha，有则带 sha 更新。
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "ConnieWCL/ai-hardware-newsletter"
API_BASE = f"https://api.github.com/repos/{REPO}/contents"

# 路径：脚本可从工作区根目录或仓库目录运行
WORKSPACE = Path(__file__).resolve().parents[2] if len(Path(__file__).resolve().parents) > 2 else Path.cwd()
# 尝试多个可能的 digest 目录
for candidate in [
    Path(__file__).resolve().parents[2] / "daily_digest",       # 工作区根
    Path(__file__).resolve().parents[1] / "data" / "plan_a",    # 仓库内
    Path.cwd() / "daily_digest",
]:
    if candidate.exists():
        DIGEST_DIR = candidate
        break
else:
    DIGEST_DIR = Path.cwd() / "daily_digest"

PAT_FILE = Path.home() / ".workbuddy" / "gh_pat.txt"
# 也检查工作区 .workbuddy 目录
WORKSPACE_PAT = Path("/Users/connie/WorkBuddy/2026-08-31-01-21-50/.workbuddy/gh_pat.txt")


def _load_pat() -> str:
    """从本地文件读取 GitHub PAT."""
    for f in [WORKSPACE_PAT, PAT_FILE]:
        if f.exists():
            pat = f.read_text().strip()
            if pat:
                return pat
    raise SystemExit(f"GitHub PAT 未找到。请将 PAT 存放在 {WORKSPACE_PAT} 或 {PAT_FILE}")


def _api(method: str, path: str, pat: str, data: dict | None = None) -> dict:
    """调用 GitHub Contents API."""
    url = f"{API_BASE}/{path}"
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}  # 文件不存在，正常情况（首次上传）
        body_text = exc.read().decode()[:500]
        raise SystemExit(f"GitHub API 错误 {exc.code}: {body_text}") from exc


def upload(date_str: str) -> bool:
    json_path = DIGEST_DIR / f"{date_str}.json"
    if not json_path.exists():
        print(f"JSON 文件不存在: {json_path}")
        return False

    pat = _load_pat()
    repo_path = f"data/plan_a/{date_str}.json"

    # 检查文件是否已存在（获取 sha 用于更新）
    existing = _api("GET", repo_path, pat)
    sha = existing.get("sha")

    content = base64.b64encode(json_path.read_bytes()).decode()
    payload = {
        "message": f"plan_a: {date_str}",
        "content": content,
    }
    if sha:
        payload["sha"] = sha

    result = _api("PUT", repo_path, pat, payload)
    commit_sha = result.get("commit", {}).get("sha", "?")[:7]
    action = "更新" if sha else "创建"
    print(f"{action}成功: {repo_path} (commit {commit_sha})")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/upload_plan_a.py YYYY-MM-DD")
        sys.exit(1)
    ok = upload(sys.argv[1])
    sys.exit(0 if ok else 1)
