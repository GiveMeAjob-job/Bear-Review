# src/summarizer.py - 🔄 增强版
import os
from collections import Counter
from typing import Dict, List, Tuple
from .notion_client import calc_xp
from .utils import setup_logger

logger = setup_logger(__name__)


class TaskSummarizer:
    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = templates_dir

    def aggregate_tasks(self, tasks: List[Dict]) -> Tuple[Dict, List[str]]:
        """聚合任务统计信息"""
        if not tasks:
            return {"total": 0, "xp": 0, "cats": {}, "mit_count": 0}, []

        xp_total = sum(calc_xp(t) for t in tasks)
        categories = Counter()
        mit_count = 0
        titles = []

        for task in tasks:
            try:
                # 分类统计
                category = (
                    task.get("properties", {})
                    .get("分类", {})
                    .get("select", {})
                    .get("name", "未分类")
                )
                categories[category] += 1

                # MIT计数
                priority = (
                    task.get("properties", {})
                    .get("优先级", {})
                    .get("select", {})
                    .get("name", "")
                )
                if priority == "MIT":
                    mit_count += 1

                # 任务标题
                title_prop = task.get("properties", {}).get("任务名称", {})
                if title_prop.get("title"):
                    title = title_prop["title"][0]["plain_text"]
                    titles.append(title)

            except (KeyError, TypeError, IndexError) as e:
                logger.warning(f"处理任务时出错: {e}, 任务ID: {task.get('id', 'unknown')}")
                continue

        stats = {
            "total": len(tasks),
            "xp": xp_total,
            "cats": dict(categories),
            "mit_count": mit_count
        }

        logger.info(f"任务聚合完成: 总数 {stats['total']}, XP {stats['xp']}, MIT {stats['mit_count']}")
        return stats, titles

    def _load_template(self, period: str) -> str:
        """加载提示词模板"""
        template_file = os.path.join(self.templates_dir, f"{period}_prompt.txt")

        if os.path.exists(template_file):
            with open(template_file, 'r', encoding='utf-8') as f:
                return f.read().strip()

        # 默认模板
        return self._get_default_template(period)

    def _get_default_template(self, period: str) -> str:
        """获取默认模板"""
        period_map = {
            "daily": ("今天", "明天", "日"),
            "weekly": ("本周", "下周", "周"),
            "monthly": ("本月", "下月", "月")
        }

        current, next_period, unit = period_map.get(period, ("今天", "明天", "日"))

        return f"""# {period.title()} Review
已完成任务 {{total}} 个，分类分布：{{categories}}，获得 XP {{xp}}，其中 MIT 任务 {{mit_count}} 个。

## 任务清单
{{task_list}}

请用中文输出，要求简洁实用：
1. **{current}亮点** - 总结 3 个主要成就
2. **改进空间** - 指出 1 个最需要优化的方面  
3. **{next_period}行动** - 提供 3 条具体可执行的建议

注意：回复字数控制在 300 字以内，重点突出可操作性。"""

    def build_prompt(self, stats: Dict, titles: List[str], period: str) -> str:
        """构建AI提示词"""
        template = self._load_template(period)

        # 格式化分类分布
        if stats["cats"]:
            categories = ", ".join(f"{k}:{v}" for k, v in stats["cats"].items())
        else:
            categories = "无"

        # 格式化任务列表
        if titles:
            task_list = "\n".join(f"- {title}" for title in titles[:20])  # 限制显示前20个
            if len(titles) > 20:
                task_list += f"\n... 还有 {len(titles) - 20} 个任务"
        else:
            task_list = "无已完成任务"

        prompt = template.format(
            total=stats["total"],
            xp=stats["xp"],
            categories=categories,
            mit_count=stats["mit_count"],
            task_list=task_list
        )

        logger.info(f"生成 {period} 提示词，长度: {len(prompt)} 字符")
        return prompt