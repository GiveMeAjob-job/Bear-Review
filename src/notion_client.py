# src/notion_client.py - 🔄 优化版
import requests
from typing import List, Dict, Optional
from datetime import date, timedelta, datetime
from .config import Config
from .utils import retry_on_failure, setup_logger

logger = setup_logger(__name__)


class NotionClient:
    def __init__(self, config: Config):
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {config.notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    @retry_on_failure(max_retries=3)
    def _query_tasks(self, start_date: date, end_date: date,
                     additional_filters: Optional[List[Dict]] = None) -> List[Dict]:
        """查询任务的通用方法（时间边界更精确）"""
        from datetime import datetime, time, timedelta
        import pytz

        # --- ✅ 核心修正：构建精确到时区的ISO 8601时间字符串 ---
        tz = pytz.timezone(self.config.timezone)

        # 查询范围的开始时间（例如：2025-06-05 00:00:00 in America/Toronto）
        start_datetime_local = tz.localize(datetime.combine(start_date, time.min))

        # 查询范围的结束时间（结束日期的后一天的0点）
        # 这样可以确保覆盖整个end_date，直到23:59:59
        end_datetime_local = tz.localize(datetime.combine(end_date + timedelta(days=1), time.min))

        # 转换为API需要的ISO 8601格式
        start_iso = start_datetime_local.isoformat()
        end_iso = end_datetime_local.isoformat()

        # --- 修改查询过滤器，使用精确时间 ---
        filters = [
            {
                "property": "计划日期",
                "date": {"on_or_after": start_iso}  # 使用带时区的完整时间
            },
            {
                "property": "计划日期",
                "date": {"before": end_iso}  # 使用 "before" 下一天的开始，确保覆盖全天
            },
            {
                "property": "状态",
                "select": {"equals": "Done"}
            }
        ]

        if additional_filters:
            filters.extend(additional_filters)

        payload = {
            "filter": {"and": filters},
            "page_size": 100,
            "sorts": [
                {
                    "property": "计划日期",
                    "direction": "ascending"
                }
            ]
        }

        url = f"https://api.notion.com/v1/databases/{self.config.notion_db_id}/query"
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()

        results = response.json().get("results", [])
        logger.info(f"查询到 {len(results)} 个任务 ({start_date} 到 {end_date})")
        return results

    def query_period_tasks(self, period: str) -> List[Dict]:
        """根据周期查询任务"""
        from .utils import get_date_range
        start_date, end_date = get_date_range(period, self.config.timezone)
        return self._query_tasks(start_date, end_date)

    @retry_on_failure(max_retries=3)
    def create_review_page(self, title: str, content: str, parent_id: str) -> str:
        """创建复盘页面"""
        payload = {
            "parent": {"page_id": parent_id},
            "properties": {
                "title": {
                    "title": [{"text": {"content": title}}]
                }
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": content}}]
                    }
                }
            ]
        }

        response = requests.post(
            "https://api.notion.com/v1/pages",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        return response.json()["id"]

    def query_three_days_tasks(self) -> Dict[str, List[Dict]]:
        """查询最近三天的任务，按天分组返回"""
        from datetime import timedelta
        import pytz

        tz = pytz.timezone(self.config.timezone)
        today = datetime.now(tz).date()

        # 获取三天的数据
        three_days_data = {}
        for days_ago in [1, 2, 3]:  # 昨天、前天、大前天
            target_date = today - timedelta(days=days_ago)
            tasks = self._query_tasks(target_date, target_date)
            three_days_data[target_date.isoformat()] = tasks

        return three_days_data

    def get_yesterday_tasks(self) -> List[Dict]:
        """获取昨天的任务（修复时区问题）"""
        from datetime import timedelta
        import pytz

        tz = pytz.timezone(self.config.timezone)
        now = datetime.now(tz)
        yesterday = (now - timedelta(days=1)).date()

        logger.info(f"🕐 当前时间: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"📅 查询昨天的任务: {yesterday}")

        return self._query_tasks(yesterday, yesterday)


def calc_xp(page: Dict) -> int:
    """计算经验值"""
    try:
        priority = (
            page.get("properties", {})
            .get("优先级", {})
            .get("select", {})
            .get("name", "")  # 默认值是空字符串
        )

        # ✅ 修正逻辑：明确判断各种情况
        if priority == "MIT":
            return 10
        elif priority:  # 如果 priority 不是空字符串 (例如 "次要")
            return 5
        else:  # 如果 priority 是空字符串，说明没有设置优先级
            return 0

    except (KeyError, TypeError):
        logger.warning(f"无法计算XP，页面数据异常: {page.get('id', 'unknown')}")
        return 0


