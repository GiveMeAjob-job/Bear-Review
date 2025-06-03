#!/usr/bin/env python3
# debug_notion.py - Notion API 调试脚本

import os, requests, json
from urllib.parse import urlparse

# ★ 新增三行 ----------------------------
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")


def test_notion_connection():
    """测试 Notion 连接和权限"""

    # 1. 检查环境变量
    print("=" * 60)
    print("1️⃣  检查环境变量")
    print("=" * 60)

    token = os.getenv("NOTION_TOKEN")
    db_id = os.getenv("NOTION_DB_ID")

    if not token:
        print("❌ NOTION_TOKEN 未设置!")
        return False
    else:
        print(f"✅ NOTION_TOKEN: {token[:10]}...{token[-5:]}")

    if not db_id:
        print("❌ NOTION_DB_ID 未设置!")
        return False
    else:
        print(f"✅ NOTION_DB_ID: {db_id}")

    # 2. 验证 DB ID 格式
    print("\n" + "=" * 60)
    print("2️⃣  验证数据库 ID 格式")
    print("=" * 60)

    # Notion DB ID 应该是 32 个字符的 UUID (不带连字符)
    clean_db_id = db_id.replace("-", "")
    if len(clean_db_id) != 32:
        print(f"⚠️  数据库 ID 长度不正确: {len(clean_db_id)} (应该是 32)")
        print("   请确保使用的是数据库 ID，而不是页面 ID")
    else:
        print("✅ 数据库 ID 格式正确")

    # 3. 测试 API 连接
    print("\n" + "=" * 60)
    print("3️⃣  测试 Notion API 连接")
    print("=" * 60)

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
    }

    # 测试用户信息
    try:
        response = requests.get("https://api.notion.com/v1/users/me", headers=headers)
        if response.status_code == 200:
            user_info = response.json()
            print(f"✅ API 连接成功! 用户: {user_info.get('name', 'Unknown')}")
        else:
            print(f"❌ API 连接失败: {response.status_code}")
            print(f"   响应: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 连接错误: {e}")
        return False

    # 4. 获取可访问的数据库列表
    print("\n" + "=" * 60)
    print("4️⃣  获取有权限访问的数据库")
    print("=" * 60)

    try:
        response = requests.post(
            "https://api.notion.com/v1/search",
            headers=headers,
            json={
                "filter": {
                    "value": "database",
                    "property": "object"
                }
            }
        )

        if response.status_code == 200:
            data = response.json()
            databases = data.get("results", [])
            print(f"📊 找到 {len(databases)} 个可访问的数据库:\n")

            target_found = False
            for db in databases:
                db_id_from_api = db["id"].replace("-", "")
                db_title = db.get("title", [{}])[0].get("plain_text", "Untitled")
                print(f"   • {db_title}")
                print(f"     ID: {db_id_from_api}")

                if db_id_from_api == clean_db_id:
                    print(f"     ✅ 这是目标数据库!")
                    target_found = True
                print()

            if not target_found:
                print(f"❌ 目标数据库 ID ({clean_db_id}) 未在可访问列表中!")
                print("\n可能的原因:")
                print("1. Integration 没有被添加到数据库")
                print("2. 数据库 ID 错误")
                print("3. 使用了页面 ID 而不是数据库 ID")
        else:
            print(f"❌ 搜索失败: {response.status_code}")
            print(f"   响应: {response.text}")

    except Exception as e:
        print(f"❌ 搜索错误: {e}")

    # 5. 尝试直接访问目标数据库
    print("\n" + "=" * 60)
    print("5️⃣  尝试访问目标数据库")
    print("=" * 60)

    try:
        # 尝试不同的 ID 格式
        for test_id in [db_id, clean_db_id]:
            print(f"\n尝试 ID: {test_id}")
            response = requests.get(
                f"https://api.notion.com/v1/databases/{test_id}",
                headers=headers
            )

            if response.status_code == 200:
                db_info = response.json()
                title = db_info.get("title", [{}])[0].get("plain_text", "Untitled")
                print(f"✅ 成功访问数据库: {title}")

                # 显示数据库属性
                print("\n📋 数据库字段:")
                properties = db_info.get("properties", {})
                for prop_name, prop_info in properties.items():
                    prop_type = prop_info.get("type", "unknown")
                    print(f"   • {prop_name} ({prop_type})")

                return True
            elif response.status_code == 404:
                print(f"❌ 404 - 数据库未找到")
            else:
                print(f"❌ 错误 {response.status_code}: {response.text}")

    except Exception as e:
        print(f"❌ 访问错误: {e}")

    # 6. 解决方案建议
    print("\n" + "=" * 60)
    print("🔧 解决方案")
    print("=" * 60)
    print("""
1. 确保在 Notion 中正确设置了 Integration:
   - 访问 https://www.notion.so/my-integrations
   - 创建新的 Integration 或使用现有的
   - 复制 Integration Token

2. 将 Integration 添加到数据库:
   - 打开你的 Task Master 数据库
   - 点击右上角的 "..." 菜单
   - 选择 "Add connections"
   - 搜索并添加你的 Integration

3. 获取正确的数据库 ID:
   - 在浏览器中打开数据库
   - URL 格式: https://www.notion.so/xxxxx?v=yyyyy
   - xxxxx 部分就是数据库 ID (32位字符)
   - 注意：不要使用 ?v= 后面的 view ID

4. 设置环境变量:
   export NOTION_TOKEN="your-integration-token"
   export NOTION_DB_ID="your-database-id"
""")

    return False


if __name__ == "__main__":
    print("🔍 Notion API 调试工具\n")
    test_notion_connection()