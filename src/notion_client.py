from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

import pytz
import requests

from .config import Config
from .models import TaskRecord
from .utils import (
    get_date_range,
    parse_notion_datetime,
    retry_on_failure,
    safe_int,
    setup_logger,
)

logger = setup_logger(__name__)


class NotionClient:
    def __init__(self, config: Config):
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {config.notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    def _build_date_range(self, start_date: date, end_date: date) -> tuple[str, str]:
        tz = pytz.timezone(self.config.timezone)
        start_datetime = tz.localize(datetime.combine(start_date, time.min))
        end_datetime = tz.localize(datetime.combine(end_date + timedelta(days=1), time.min))
        return start_datetime.isoformat(), end_datetime.isoformat()

    @retry_on_failure(max_retries=3)
    def _query_tasks(
        self,
        start_date: date,
        end_date: date,
        additional_filters: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        start_iso, end_iso = self._build_date_range(start_date, end_date)
        filters = [
            {"property": "计划日期", "date": {"on_or_after": start_iso}},
            {"property": "计划日期", "date": {"before": end_iso}},
            {"property": "状态", "select": {"equals": "Done"}},
        ]

        if additional_filters:
            filters.extend(additional_filters)

        payload = {
            "filter": {"and": filters},
            "page_size": 100,
            "sorts": [{"property": "计划日期", "direction": "ascending"}],
        }

        results: List[Dict] = []
        next_cursor: Optional[str] = None
        has_more = True
        url = f"https://api.notion.com/v1/databases/{self.config.notion_db_id}/query"

        while has_more:
            request_payload = dict(payload)
            if next_cursor:
                request_payload["start_cursor"] = next_cursor

            response = requests.post(url, headers=self.headers, json=request_payload, timeout=20)
            response.raise_for_status()

            body = response.json()
            results.extend(body.get("results", []))
            has_more = body.get("has_more", False)
            next_cursor = body.get("next_cursor")

        logger.info("查询到 %s 个任务 (%s 到 %s)", len(results), start_date, end_date)
        return results

    def query_period_tasks(self, period: str) -> List[Dict]:
        start_date, end_date = get_date_range(period, self.config.timezone)
        return self._query_tasks(start_date, end_date)

    def fetch_period_tasks(self, period: str) -> List[TaskRecord]:
        return [self.parse_task(page) for page in self.query_period_tasks(period)]

    def fetch_tasks_for_date(self, target_date: date) -> List[TaskRecord]:
        return [self.parse_task(page) for page in self._query_tasks(target_date, target_date)]

    def fetch_yesterday_tasks(self) -> List[TaskRecord]:
        tz = pytz.timezone(self.config.timezone)
        yesterday = datetime.now(tz).date() - timedelta(days=1)
        return self.fetch_tasks_for_date(yesterday)

    def fetch_recent_tasks(self, days: int) -> List[TaskRecord]:
        if days <= 0:
            return []

        tz = pytz.timezone(self.config.timezone)
        end_date = datetime.now(tz).date()
        start_date = end_date - timedelta(days=days - 1)
        return [self.parse_task(page) for page in self._query_tasks(start_date, end_date)]

    @retry_on_failure(max_retries=3)
    def create_review_page(self, title: str, content: str, parent_id: str) -> str:
        payload = {
            "parent": {"page_id": parent_id},
            "properties": {
                "title": {"title": [{"text": {"content": title}}]}
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": content}}]},
                }
            ],
        }

        response = requests.post(
            "https://api.notion.com/v1/pages",
            headers=self.headers,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()["id"]

    def query_three_days_tasks(self) -> Dict[str, List[Dict]]:
        tz = pytz.timezone(self.config.timezone)
        today = datetime.now(tz).date()
        three_days_data = {}

        for days_ago in [1, 2, 3]:
            target_date = today - timedelta(days=days_ago)
            three_days_data[target_date.isoformat()] = self._query_tasks(target_date, target_date)

        return three_days_data

    def get_yesterday_tasks(self) -> List[Dict]:
        tz = pytz.timezone(self.config.timezone)
        now = datetime.now(tz)
        yesterday = now.date() - timedelta(days=1)
        logger.info("🕐 当前时间: %s", now.strftime("%Y-%m-%d %H:%M:%S %Z"))
        logger.info("📅 查询昨天的任务: %s", yesterday)
        return self._query_tasks(yesterday, yesterday)

    @staticmethod
    def parse_task(page: Dict) -> TaskRecord:
        props = page.get("properties", {})
        title = "".join(
            segment.get("plain_text", "")
            for segment in props.get("任务名称", {}).get("title", [])
        ).strip() or "（无标题）"
        category = props.get("分类", {}).get("select", {}).get("name") or "未分类"
        priority = props.get("优先级", {}).get("select", {}).get("name") or ""
        status = props.get("状态", {}).get("select", {}).get("name") or ""

        date_prop = props.get("计划日期", {}).get("date", {}) or {}
        start_at = parse_notion_datetime(date_prop.get("start"))
        end_at = parse_notion_datetime(date_prop.get("end")) or start_at

        xp_value = props.get("XP", {}).get("formula", {}).get("number")
        if xp_value is None:
            xp_value = _priority_to_xp(priority)

        return TaskRecord(
            id=page.get("id", ""),
            title=title,
            category=category,
            priority=priority,
            status=status,
            scheduled_start=start_at,
            scheduled_end=end_at,
            xp=safe_int(xp_value),
            tomatoes=safe_int(props.get("番茄数", {}).get("formula", {}).get("number")),
            actual_minutes=safe_int(
                props.get("实际用时(min)", {}).get("formula", {}).get("number")
            ),
            raw=page,
        )


def calc_xp(page: Dict) -> int:
    try:
        props = page.get("properties", {})
        xp_value = props.get("XP", {}).get("formula", {}).get("number")
        if xp_value is not None:
            return safe_int(xp_value)

        priority = props.get("优先级", {}).get("select", {}).get("name", "")
        return _priority_to_xp(priority)
    except (KeyError, TypeError):
        logger.warning("无法计算XP，页面数据异常: %s", page.get("id", "unknown"))
        return 0


def _priority_to_xp(priority: str) -> int:
    if priority == "MIT":
        return 10
    if priority:
        return 5
    return 0
