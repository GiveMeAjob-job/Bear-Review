# src/utils.py - 🆕 工具函数
import logging
import time
from functools import wraps
from datetime import datetime, date
import pytz


def setup_logger(name: str = "task_master") -> logging.Logger:
    """设置日志记录器"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    logging.warning(f"尝试 {attempt + 1} 失败: {e}, 重试中...")
                    time.sleep(delay * (2 ** attempt))  # 指数退避
            return None

        return wrapper

    return decorator


def get_date_range(period: str, timezone: str = "Asia/Shanghai") -> tuple[date, date]:
    """获取日期范围"""
    tz = pytz.timezone(timezone)
    now = datetime.now(tz).date()

    if period == "daily":
        return now, now
    elif period == "weekly":
        start = now - timedelta(days=now.weekday())
        end = start + timedelta(days=6)
        return start, end
    elif period == "monthly":
        start = now.replace(day=1)
        if start.month == 12:
            next_month = date(start.year + 1, 1, 1)
        else:
            next_month = date(start.year, start.month + 1, 1)
        end = next_month - timedelta(days=1)
        return start, end
    else:
        raise ValueError(f"不支持的周期: {period}")