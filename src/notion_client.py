# src/notion_client.py - 🔄 优化版
import requests
from typing import List, Dict, Optional
from datetime import date, timedelta
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
        """查询任务的通用方法"""
        filters = [
            {
                "property": "计划日期",
                "date": {"on_or_after": start_date.isoformat()}
            },
            {
                "property": "计划日期",
                "date": {"on_or_before": end_date.isoformat()}
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
            "page_size": 100,  # 批量获取
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