# src/notifier.py - 支持两个不同的Bot
import smtplib
import requests
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, List, Tuple
from .config import Config
from .utils import retry_on_failure, setup_logger

logger = setup_logger(__name__)


class Notifier:
    def __init__(self, config: Config):
        self.config = config

    def _clean_markdown(self, text: str) -> str:
        """清理文本中的Markdown格式"""
        # 移除加粗标记 **text** 或 __text__
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)

        # 移除斜体标记 *text* 或 _text_
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)

        # 移除代码标记 `code`
        text = re.sub(r'`(.+?)`', r'\1', text)

        # 移除标题标记 # ## ###
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)

        # 移除引用标记 >
        text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)

        # 移除链接 [text](url)
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)

        # 移除图片 ![alt](url)
        text = re.sub(r'!\[.*?\]\(.+?\)', '', text)

        # 移除水平线 --- 或 ***
        text = re.sub(r'^(\*{3,}|_{3,}|-{3,})$', '', text, flags=re.MULTILINE)

        # 移除列表标记但保留缩进
        text = re.sub(r'^(\s*)[*+-]\s+', r'\1• ', text, flags=re.MULTILINE)
        text = re.sub(r'^(\s*)\d+\.\s+', r'\1• ', text, flags=re.MULTILINE)

        return text.strip()

    @retry_on_failure(max_retries=2)
    def send_telegram_with_token(self, message: str, title: str = "",
                                 bot_token: str = None, chat_id: str = None) -> bool:
        """使用指定的bot token发送消息到指定chat_id"""

        if not (bot_token and chat_id):
            logger.warning(f"Telegram配置不完整，跳过推送")
            return False

        try:
            # 清理消息中的Markdown格式
            clean_message = self._clean_markdown(message)

            # 构建消息
            if title:
                clean_title = self._clean_markdown(title)
                full_message = f"📋 {clean_title}\n{'─' * 30}\n\n{clean_message}"
            else:
                full_message = clean_message

            # 限制消息长度（Telegram 限制 4096 字符）
            if len(full_message) > 8000:
                full_message = full_message[:7997] + "..."

            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

            # 确保 chat_id 是整数
            try:
                chat_id_int = int(chat_id)
            except (ValueError, TypeError):
                logger.error(f"无效的 Telegram Chat ID: {chat_id}")
                return False

            payload = {
                "chat_id": chat_id_int,
                "text": full_message
            }

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                logger.info(f"Telegram通知发送成功到 {chat_id}")
                return True
            else:
                logger.error(f"Telegram API 错误 {response.status_code}: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Telegram通知发送失败: {e}")
            return False

    def notify_all(self, title: str, content: str) -> Dict[str, bool]:
        """发送所有可用的通知"""
        results = {}

        # 发送到主账号（使用主Bot）
        if self.config.telegram_bot_token and self.config.telegram_chat_id:
            logger.info(f"发送到主账号 (Bot 1): ...{self.config.telegram_chat_id[-4:]}")
            success = self.send_telegram_with_token(
                content, title,
                self.config.telegram_bot_token,
                self.config.telegram_chat_id
            )
            results[f'telegram_{self.config.telegram_chat_id}'] = success

        # 发送到副账号（使用副Bot或主Bot）
        if self.config.telegram_chat_id_2:
            # 如果有专用的第二个Bot token，使用它；否则使用主Bot token
            bot_token_2 = self.config.telegram_bot_token_2 or self.config.telegram_bot_token

            if bot_token_2:
                logger.info(
                    f"发送到副账号 (Bot {'2' if self.config.telegram_bot_token_2 else '1'}): ...{self.config.telegram_chat_id_2[-4:]}")
                success = self.send_telegram_with_token(
                    content, title,
                    bot_token_2,
                    self.config.telegram_chat_id_2
                )
                results[f'telegram_{self.config.telegram_chat_id_2}'] = success
            else:
                logger.warning("副账号配置不完整，跳过发送")
                results[f'telegram_{self.config.telegram_chat_id_2}'] = False

        # 邮件通知
        if all([self.config.email_smtp_server, self.config.email_username, self.config.email_password]):
            results['email'] = self.send_email(title, content)
        else:
            results['email'] = False

        return results

    @retry_on_failure(max_retries=2)
    def send_email(self, subject: str, content: str, to_email: Optional[str] = None) -> bool:
        """发送邮件通知"""
        if not all([self.config.email_smtp_server, self.config.email_username, self.config.email_password]):
            logger.warning("邮件配置不完整，跳过发送")
            return False

        try:
            # 清理内容中的Markdown
            clean_content = self._clean_markdown(content)

            msg = MIMEMultipart()
            msg['From'] = self.config.email_username
            msg['To'] = to_email or self.config.email_username
            msg['Subject'] = subject

            msg.attach(MIMEText(clean_content, 'plain', 'utf-8'))

            with smtplib.SMTP(self.config.email_smtp_server, 587) as server:
                server.starttls()
                server.login(self.config.email_username, self.config.email_password)
                server.send_message(msg)

            logger.info(f"邮件发送成功: {subject}")
            return True

        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False