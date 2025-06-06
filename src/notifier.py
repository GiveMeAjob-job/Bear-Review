# src/notifier.py - 修复Markdown和支持多个Telegram账号
import smtplib
import requests
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, List
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
    def send_telegram(self, message: str, title: str = "", chat_id: Optional[str] = None) -> bool:
        """发送Telegram通知到指定chat_id"""
        bot_token = self.config.telegram_bot_token
        target_chat_id = chat_id or self.config.telegram_chat_id

        if not (bot_token and target_chat_id):
            logger.warning(f"Telegram配置不完整，跳过推送到 {target_chat_id}")
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
            if len(full_message) > 4000:
                full_message = full_message[:3997] + "..."

            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

            # 确保 chat_id 是整数
            try:
                chat_id_int = int(target_chat_id)
            except (ValueError, TypeError):
                logger.error(f"无效的 Telegram Chat ID: {target_chat_id}")
                return False

            payload = {
                "chat_id": chat_id_int,
                "text": full_message
                # 不设置 parse_mode，让Telegram使用默认的纯文本模式
            }

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                logger.info(f"Telegram通知发送成功到 {target_chat_id}")
                return True
            else:
                logger.error(f"Telegram API 错误 {response.status_code}: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Telegram通知发送失败: {e}")
            return False

    def send_telegram_multiple(self, message: str, title: str = "", chat_ids: List[str] = None) -> Dict[str, bool]:
        """发送到多个Telegram账号"""
        results = {}

        # 如果没有提供chat_ids列表，使用默认的
        if not chat_ids:
            # 尝试从环境变量获取多个chat_id
            primary_chat_id = self.config.telegram_chat_id
            secondary_chat_id = self.config.telegram_chat_id_2  # 需要在config中添加

            chat_ids = [primary_chat_id]
            if secondary_chat_id:
                chat_ids.append(secondary_chat_id)

        # 发送到每个chat_id
        for chat_id in chat_ids:
            if chat_id:
                results[chat_id] = self.send_telegram(message, title, chat_id)

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

    def notify_all(self, title: str, content: str) -> Dict[str, bool]:
        """发送所有可用的通知"""
        results = {}

        # Telegram通知 - 发送到多个账号
        if self.config.telegram_bot_token:
            # 获取所有chat_ids
            chat_ids = []

            # 主账号
            if self.config.telegram_chat_id:
                chat_ids.append(self.config.telegram_chat_id)
                logger.info(f"添加主Telegram账号: ...{self.config.telegram_chat_id[-4:]}")

            # 副账号（如果存在）
            if hasattr(self.config, 'telegram_chat_id_2') and self.config.telegram_chat_id_2:
                chat_ids.append(self.config.telegram_chat_id_2)
                logger.info(f"添加副Telegram账号: ...{self.config.telegram_chat_id_2[-4:]}")
            else:
                logger.info("未配置副Telegram账号 (TELEGRAM_CHAT_ID_2)")

            logger.info(f"准备发送到 {len(chat_ids)} 个Telegram账号")

            # 发送到所有账号
            telegram_results = self.send_telegram_multiple(content, title, chat_ids)

            # 合并结果
            for chat_id, success in telegram_results.items():
                results[f'telegram_{chat_id}'] = success
        else:
            results['telegram'] = False

        # 邮件通知
        if all([self.config.email_smtp_server, self.config.email_username, self.config.email_password]):
            results['email'] = self.send_email(title, content)
        else:
            results['email'] = False

        return results