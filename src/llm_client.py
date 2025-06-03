# src/llm_client.py
import openai, os
openai.api_key = os.getenv("DEEPSEEK_KEY")

def ask_llm(prompt):
    resp = openai.ChatCompletion.create(
        model="deepseek-chat",
        messages=[{"role":"user","content": prompt}],
        max_tokens=500, temperature=0.7)
    return resp.choices[0].message.content
