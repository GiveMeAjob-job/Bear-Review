from openai import AsyncOpenAI
from app.core.settings import ai_settings

async def chat_complete(prompt: str) -> str:
    if ai_settings.llm_provider == 'openai':
        client = AsyncOpenAI(api_key=ai_settings.openai_api_key)
        resp = await client.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=[{'role': 'user', 'content': prompt}],
        )
        return resp.choices[0].message.content.strip()
    raise ValueError('provider?')
