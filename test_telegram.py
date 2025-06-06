#!/usr/bin/env python3
"""
Telegram 发送测试脚本
用于测试Bot是否能向特定Chat ID发送消息
"""

import os
import requests
from dotenv import load_dotenv
from datetime import datetime

# 加载环境变量
load_dotenv()


def test_telegram_send(bot_token, chat_id, message=None):
    """测试向指定chat_id发送消息"""

    if not bot_token or not chat_id:
        print(
            f"❌ 缺少必要参数: bot_token={'已设置' if bot_token else '未设置'}, chat_id={'已设置' if chat_id else '未设置'}")
        return False

    # 默认测试消息
    if message is None:
        message = f"""🧪 Telegram Bot 测试消息

时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Chat ID: {chat_id}

这是一条测试消息，用于验证Bot是否能正常发送消息到此账号。

如果您收到了这条消息，说明配置正确！✅"""

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    try:
        # 先尝试获取Bot信息
        bot_info_url = f"https://api.telegram.org/bot{bot_token}/getMe"
        bot_response = requests.get(bot_info_url, timeout=10)

        if bot_response.status_code == 200:
            bot_data = bot_response.json()
            if bot_data.get('ok'):
                bot_name = bot_data['result']['username']
                print(f"✅ Bot连接成功: @{bot_name}")
            else:
                print(f"❌ Bot验证失败: {bot_data}")
                return False
        else:
            print(f"❌ 无法连接到Bot: HTTP {bot_response.status_code}")
            return False

        # 尝试发送消息
        print(f"📤 正在发送消息到 Chat ID: {chat_id}")

        payload = {
            "chat_id": chat_id,
            "text": message
        }

        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                print(f"✅ 消息发送成功!")
                print(f"   消息ID: {result['result']['message_id']}")
                print(f"   发送时间: {datetime.fromtimestamp(result['result']['date']).strftime('%Y-%m-%d %H:%M:%S')}")
                return True
            else:
                print(f"❌ 发送失败: {result}")
                return False
        else:
            error_data = response.json()
            print(f"❌ HTTP错误 {response.status_code}: {error_data}")

            # 提供具体的错误说明
            if "chat not found" in str(error_data):
                print("\n💡 解决方案:")
                print("   1. 确保Chat ID正确")
                print("   2. 如果是私聊，用户需要先向Bot发送 /start")
                print("   3. 如果是群组，需要先将Bot加入群组")
                print("   4. 使用 @userinfobot 获取正确的Chat ID")
            elif "bot was blocked" in str(error_data):
                print("\n💡 用户已屏蔽Bot，需要用户解除屏蔽")
            elif "not enough rights" in str(error_data):
                print("\n💡 Bot在群组中没有发送消息的权限")

            return False

    except requests.exceptions.Timeout:
        print("❌ 请求超时，请检查网络连接")
        return False
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        return False


def main():
    """主函数"""
    print("🔧 Telegram Bot 发送测试工具\n")

    # 从环境变量读取配置
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id_1 = os.getenv("TELEGRAM_CHAT_ID")
    chat_id_2 = os.getenv("TELEGRAM_CHAT_ID_2")

    if not bot_token:
        print("❌ 请在 .env 文件中设置 TELEGRAM_BOT_TOKEN")
        print("\n示例 .env 文件内容:")
        print("TELEGRAM_BOT_TOKEN=123456789:ABCdefghijklmnopqrstuvwxyz")
        print("TELEGRAM_CHAT_ID=111111111")
        print("TELEGRAM_CHAT_ID_2=222222222")
        return

    # 测试主账号
    if chat_id_1:
        print(f"=" * 50)
        print(f"测试主账号 (TELEGRAM_CHAT_ID)")
        print(f"=" * 50)
        test_telegram_send(bot_token, chat_id_1)
    else:
        print("⚠️  未设置 TELEGRAM_CHAT_ID")

    # 测试副账号
    if chat_id_2:
        print(f"\n" + "=" * 50)
        print(f"测试副账号 (TELEGRAM_CHAT_ID_2)")
        print(f"=" * 50)
        test_telegram_send(bot_token, chat_id_2)
    else:
        print("\n⚠️  未设置 TELEGRAM_CHAT_ID_2")

    # 手动测试特定Chat ID
    print(f"\n" + "=" * 50)
    print("手动测试特定Chat ID（输入q退出）")
    print(f"=" * 50)

    while True:
        test_chat_id = input("\n请输入要测试的Chat ID (或 'q' 退出): ").strip()
        if test_chat_id.lower() == 'q':
            break

        if test_chat_id:
            # 确保是数字或负数
            try:
                # 验证是否为有效的chat_id
                int(test_chat_id)
                test_telegram_send(bot_token, test_chat_id)
            except ValueError:
                print("❌ 无效的Chat ID，应该是数字")


if __name__ == "__main__":
    main()