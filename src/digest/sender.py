"""邮件发送：SMTP SSL（163 等邮箱），环境变量注入凭据."""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from .config_loader import env, load_config

log = logging.getLogger(__name__)


def send(html_body: str, subject: str | None = None) -> None:
    cfg = load_config()
    user = env("SMTP_USER")
    password = env("SMTP_PASS")  # 163 需使用授权码而非登录密码
    to = [x.strip() for x in env("DIGEST_TO").split(",") if x.strip()]
    if not (user and password and to):
        raise RuntimeError("缺少 SMTP_USER / SMTP_PASS / DIGEST_TO 环境变量")

    mail = cfg["email"]
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject or f"{mail['subject_prefix']} - {__import__('time').strftime('%Y-%m-%d')}"
    msg["From"] = f"{mail['from_name']} <{user}>"
    msg["To"] = ", ".join(to)

    host = env("SMTP_HOST", mail["smtp_host"])
    port = int(env("SMTP_PORT", str(mail["smtp_port"])))
    with smtplib.SMTP_SSL(host, port, timeout=30) as server:
        server.login(user, password)
        server.sendmail(user, to, msg.as_string())
    log.info("日报已发送至 %s", to)
