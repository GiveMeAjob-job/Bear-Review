from typing import List, Dict
import llm_client


def build_prompt(stats: Dict, titles: List[str], header: str, highlight: str, next_period: str) -> str:
    cat_lines = ", ".join(f"{k}:{v}" for k, v in stats["cats"].items())
    tasks_txt = "\n".join(f"- {t}" for t in titles)
    return (
        f"# {header}\n"
        f"\u5df2\u5b8c\u6210\u4efb\u52a1 {stats['total']} \u4e2a\uff0c\u5206\u7c7b\u5206\u5e03\uff1a{cat_lines}\uff0c\u83b7\u5f97 XP {stats['xp']}\u3002\n"
        f"## \u4efb\u52a1\u6e05\u5355\n{tasks_txt}\n\n"
        f"\u8bf7\u7528\u4e2d\u6587\u8f93\u51fa\uff1a\n"
        f"1. \u5f52\u7ed3{highlight} 3 \u4e2a\u4eae\u70b9\n"
        f"2. 1 \u4e2a\u6700\u5927\u6539\u8fdb\u70b9\n"
        f"3. {next_period} 3 \u6761\u884c\u52a8\u5efa\u8bae\uff08\u4fdd\u6301\u5177\u4f53\u53ef\u6267\u884c\uff09"
    )


def ask_summary(prompt: str) -> str:
    return llm_client.ask_llm(prompt)
