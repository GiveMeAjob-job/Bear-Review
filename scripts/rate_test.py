import asyncio
import os
import httpx
from typing import List

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
}


async def fetch(client: httpx.AsyncClient, i: int) -> int:
    try:
        r = await client.get("https://api.notion.com/v1/databases", headers=HEADERS)
        return r.status_code
    except Exception:
        return 0


async def main():
    async with httpx.AsyncClient() as client:
        tasks = [asyncio.create_task(fetch(client, i)) for i in range(10)]
        codes: List[int] = await asyncio.gather(*tasks)
    print("429 count", sum(1 for c in codes if c == 429))


if __name__ == "__main__":
    asyncio.run(main())
