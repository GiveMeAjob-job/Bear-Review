"""
test_non_stream.py
简易功能：演示 DeepSeek-Reasoner 非流式调用 + 多轮对话
"""

import os
from openai import OpenAI

# ---------------------------------------------------------------------
# 1️⃣  准备 Client
# ---------------------------------------------------------------------
api_key = os.getenv("DEEPSEEK_API_KEY", "")
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)

# ---------------------------------------------------------------------
# 2️⃣  Round 1
# ---------------------------------------------------------------------
messages = [
    {"role": "user", "content": "9.11 and 9.8, which is greater?"}
]

resp1 = client.chat.completions.create(
    model="deepseek-reasoner",
    messages=messages            # stream 默认为 False
)

# DeepSeek-Reasoner 的回复结构
msg1 = resp1.choices[0].message
print("\n[Round 1]  Reasoning:", msg1.reasoning_content.strip())
print("[Round 1]  Answer    :", msg1.content.strip())

# ---------------------------------------------------------------------
# 3️⃣  Round 2（把 Assistant 回复追加进 messages）
# ---------------------------------------------------------------------
messages.append({"role": "assistant", "content": msg1.content})
messages.append({"role": "user", "content": "How many Rs are there in the word 'strawberry'?"})

resp2 = client.chat.completions.create(
    model="deepseek-reasoner",
    messages=messages
)

msg2 = resp2.choices[0].message
print("\n[Round 2]  Reasoning:", msg2.reasoning_content.strip())
print("[Round 2]  Answer    :", msg2.content.strip())
