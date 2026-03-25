import logging
import time
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Optional

import pytz


def setup_logger(name: str = "bear_review") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(handler)

    return logger


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if attempt == max_retries - 1:
                        raise
                    logging.warning("尝试 %s 失败: %s，准备重试", attempt + 1, exc)
                    time.sleep(delay * (2**attempt))
            return None

        return wrapper

    return decorator


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_notion_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return pytz.utc.localize(parsed)
    return parsed


def safe_int(value: object, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def get_local_today(timezone: str) -> date:
    return datetime.now(pytz.timezone(timezone)).date()


def get_date_range(period: str, timezone: str = "America/Toronto") -> tuple[date, date]:
    today = get_local_today(timezone)

    if period == "daily":
        return today, today

    if period == "three-days":
        return today - timedelta(days=3), today - timedelta(days=1)

    if period == "weekly":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)

    if period == "monthly":
        start = today.replace(day=1)
        if start.month == 12:
            next_month = date(start.year + 1, 1, 1)
        else:
            next_month = date(start.year, start.month + 1, 1)
        return start, next_month - timedelta(days=1)

    raise ValueError(f"不支持的周期: {period}")
