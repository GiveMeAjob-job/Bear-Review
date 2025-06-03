# src/notifier.py - 🆕 通知推送
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from .config import Config
from .utils import retry_on_failure, setup_logger

logger = setup_logger(__name__)


class Notifier:
    def __init__(self, config: Config):
        self.config = config

    @retry_on_failure(max_retries=2)
    def send_telegram(self, message: str, title: str = "") -> bool:
        """发送Telegram通知"""
        if not (self.config.telegram_bot_token and self.config.telegram_chat_id):
            logger.warning("Telegram配置不完整，跳过推送")
            return False

        try:
            full_message = f"*{title}*\n\n{message}" if title else message
            url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"

            payload = {
                "chat_id": self.config.telegram_chat_id,
                "text": full_message,
                "parse_mode": "Markdown"
            }

            response = requests.post(url, json=payload)
            response.raise_for_status()
            logger.info("Telegram通知发送成功")
            return True

        except Exception as e:
            logger.error(f"Telegram通知发送失败: {e}")
            return False

    @retry_on_failure(max_retries=2)
    def send_email(self, subject: str, content: str, to_email: Optional[str] = None) -> bool:
        """发送邮件通知"""
        if not all([self.config.email_smtp_server, self.config.email_username, self.config.email_password]):
            logger.warning("邮件配置不完整，跳过发送")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = self.config.email_username
            msg['To'] = to_email or self.config.email_username
            msg['Subject'] = subject

            msg.attach(MIMEText(content, 'plain', 'utf-8'))

            with smtplib.SMTP(self.config.email_smtp_server, 587) as server:
                server.starttls()
                server.login(self.config.email_username, self.config.email_password)
                server.send_message(msg)

            logger.info(f"邮件发送成功: {subject}")
            return True

        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False

    def notify_all(self, title: str, content: str) -> Dict[str, bool]:
        """发送所有可用的通知"""
        results = {}

        # Telegram通知
        results['telegram'] = self.send_telegram(content, title)

        # 邮件通知
        results['email'] = self.send_email(title, content)

        return results
