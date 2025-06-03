# src/notifier.py - 通知推送（修复版）
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict
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
            # 构建消息，避免 Markdown 解析错误
            if title:
                full_message = f"*{self._escape_markdown(title)}*\n\n{self._escape_markdown(message)}"
            else:
                full_message = self._escape_markdown(message)

            # 限制消息长度（Telegram 限制 4096 字符）
            if len(full_message) > 4000:
                full_message = full_message[:3997] + "..."

            url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"

            payload = {
                "chat_id": self.config.telegram_chat_id,
                "text": full_message,
                "parse_mode": "Markdown"
            }

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                logger.info("Telegram通知发送成功")
                return True
            else:
                logger.error(f"Telegram API 错误 {response.status_code}: {response.text}")

                # 如果 Markdown 解析失败，尝试纯文本
                if "can't parse entities" in response.text.lower():
                    logger.info("Markdown 解析失败，尝试纯文本发送")
                    payload["parse_mode"] = None
                    payload["text"] = f"{title}\n\n{message}" if title else message
                    response = requests.post(url, json=payload, timeout=10)

                    if response.status_code == 200:
                        logger.info("Telegram通知发送成功（纯文本）")
                        return True

                return False

        except Exception as e:
            logger.error(f"Telegram通知发送失败: {e}")
            return False

    def _escape_markdown(self, text: str) -> str:
        """转义 Markdown 特殊字符"""
        # Telegram Markdown v1 需要转义的字符
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

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
        if self.config.telegram_bot_token and self.config.telegram_chat_id:
            results['telegram'] = self.send_telegram(content, title)
        else:
            results['telegram'] = False

        # 邮件通知
        if all([self.config.email_smtp_server, self.config.email_username, self.config.email_password]):
            results['email'] = self.send_email(title, content)
        else:
            results['email'] = False

        return results