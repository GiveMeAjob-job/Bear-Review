# scripts/setup_notion.py - Notion 设置辅助脚本
"""
Notion 数据库设置辅助脚本
用于验证 Notion 集成配置和数据库结构
"""

import os
import sys
import requests
from typing import Dict, List


def check_notion_connection(token: str) -> bool:
    """检查 Notion 连接"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
    }

    try:
        response = requests.get("https://api.notion.com/v1/users/me", headers=headers)
        response.raise_for_status()
        user_info = response.json()
        print(f"✅ Notion 连接成功！用户: {user_info.get('name', 'Unknown')}")
        return True
    except requests.RequestException as e:
        print(f"❌ Notion 连接失败: {e}")
        return False


def check_database_structure(token: str, db_id: str) -> bool:
    """检查数据库结构"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
    }

    required_fields = {
        "任务名称": "title",
        "分类": "select",
        "优先级": "select",
        "状态": "select",
        "计划日期": "date"
    }

    try:
        response = requests.get(f"https://api.notion.com/v1/databases/{db_id}", headers=headers)
        response.raise_for_status()

        db_info = response.json()
        properties = db_info.get("properties", {})

        print(f"📊 数据库名称: {db_info.get('title', [{}])[0].get('plain_text', 'Unknown')}")
        print("🔍 字段检查:")

        missing_fields = []
        for field_name, field_type in required_fields.items():
            if field_name in properties:
                actual_type = properties[field_name].get("type")
                if actual_type == field_type:
                    print(f"  ✅ {field_name} ({field_type})")
                else:
                    print(f"  ⚠️  {field_name} (期望: {field_type}, 实际: {actual_type})")
            else:
                print(f"  ❌ {field_name} (缺失)")
                missing_fields.append(field_name)

        if missing_fields:
            print(f"\n⚠️  缺失字段: {', '.join(missing_fields)}")
            print("请在 Notion 数据库中创建这些字段")
            return False
        else:
            print("\n✅ 数据库结构验证通过！")
            return True

    except requests.RequestException as e:
        print(f"❌ 数据库检查失败: {e}")
        return False


def main():
    """主函数"""
    print("🔧 Task Master AI - Notion 配置检查工具\n")

    # 获取环境变量
    token = os.getenv("NOTION_TOKEN")
    db_id = os.getenv("NOTION_DB_ID")

    if not token:
        print("❌ 请设置 NOTION_TOKEN 环境变量")
        sys.exit(1)

    if not db_id:
        print("❌ 请设置 NOTION_DB_ID 环境变量")
        sys.exit(1)

    # 检查连接
    if not check_notion_connection(token):
        sys.exit(1)

    print()

    # 检查数据库结构
    if not check_database_structure(token, db_id):
        sys.exit(1)

    print("\n🎉 所有检查通过！系统已准备就绪。")


if __name__ == "__main__":
    main()