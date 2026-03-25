import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Optional

import requests

from .config import Config, TelegramTarget
from .models import ReviewReport
from .utils import retry_on_failure, setup_logger

logger = setup_logger(__name__)


class TelegramChannel:
    def __init__(self, target: TelegramTarget, message_limit: int):
        self.target = target
        self.message_limit = message_limit

    @property
    def name(self) -> str:
        return self.target.name

    @retry_on_failure(max_retries=2)
    def send(self, message: str, title: str = "") -> bool:
        clean_message = Notifier.clean_markdown(message)
        clean_title = Notifier.clean_markdown(title)
        full_message = (
            f"📋 {clean_title}\n{'─' * 24}\n\n{clean_message}"
            if clean_title
            else clean_message
        )
        if len(full_message) > self.message_limit:
            full_message = full_message[: self.message_limit - 1].rstrip() + "…"

        try:
            chat_id = int(self.target.chat_id)
        except (TypeError, ValueError):
            logger.error("无效的 Telegram Chat ID: %s", self.target.chat_id)
            return False

        response = requests.post(
            f"https://api.telegram.org/bot{self.target.bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": full_message, "disable_web_page_preview": True},
            timeout=10,
        )
        if response.status_code == 200:
            logger.info("Telegram 通知发送成功: %s", self.target.name)
            return True

        logger.error("Telegram API 错误 %s: %s", response.status_code, response.text)
        return False


class EmailChannel:
    def __init__(self, config: Config):
        self.config = config

    @property
    def name(self) -> str:
        return "email"

    @retry_on_failure(max_retries=2)
    def send(self, subject: str, content: str, to_email: Optional[str] = None) -> bool:
        if not self.config.email_enabled:
            logger.warning("邮件配置不完整，跳过发送")
            return False

        message = MIMEMultipart()
        message["From"] = self.config.email_username
        message["To"] = to_email or self.config.email_username
        message["Subject"] = subject
        message.attach(MIMEText(Notifier.clean_markdown(content), "plain", "utf-8"))

        with smtplib.SMTP(self.config.email_smtp_server, 587) as server:
            server.starttls()
            server.login(self.config.email_username, self.config.email_password)
            server.send_message(message)

        logger.info("邮件发送成功: %s", subject)
        return True


class Notifier:
    def __init__(self, config: Config):
        self.config = config
        self.channels = self._build_channels()

    @staticmethod
    def clean_markdown(text: str) -> str:
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"_(.+?)_", r"\1", text)
        text = re.sub(r"`(.+?)`", r"\1", text)
        text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
        text = re.sub(r"!\[.*?\]\(.+?\)", "", text)
        text = re.sub(r"^(\*{3,}|_{3,}|-{3,})$", "", text, flags=re.MULTILINE)
        text = re.sub(r"^(\s*)[*+-]\s+", r"\1• ", text, flags=re.MULTILINE)
        text = re.sub(r"^(\s*)\d+\.\s+", r"\1• ", text, flags=re.MULTILINE)
        return text.strip()

    def _build_channels(self):
        channels = [
            TelegramChannel(target, self.config.telegram_message_limit)
            for target in self.config.telegram_targets()
        ]
        if self.config.email_enabled:
            channels.append(EmailChannel(self.config))
        return channels

    def notify_report(self, report: ReviewReport) -> Dict[str, bool]:
        if not self.config.notifications_enabled:
            logger.info("通知模式为 disabled，本次不发送通知")
            return {"notifications_disabled": True}

        delivery_policy = (report.signals or {}).get("delivery_policy", "normal")
        if delivery_policy == "suppress":
            logger.info("自动熄火已生效，本次保持静默")
            return {"dormancy_suppressed": True}

        if delivery_policy == "restart_nudge":
            content = report.decision_card or report.preview
            return self.notify_all(report.title, content)

        if self.config.notification_mode == "full":
            content = report.content
        elif self.config.notification_mode == "smart":
            should_notify = (report.signals or {}).get("should_notify", True)
            if not should_notify:
                logger.info("smart 模式判定为无需打断，本次不发送通知")
                return {"smart_suppressed": True}
            content = report.decision_card or report.preview
        else:
            content = report.preview
        return self.notify_all(report.title, content)

    def notify_all(self, title: str, content: str) -> Dict[str, bool]:
        if not self.channels:
            logger.warning("没有可用的通知渠道")
            return {}

        results: Dict[str, bool] = {}
        for channel in self.channels:
            if isinstance(channel, EmailChannel):
                results[channel.name] = channel.send(title, content)
            else:
                results[channel.name] = channel.send(content, title)
        return results
