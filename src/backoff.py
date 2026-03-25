import asyncio


async def exponential_backoff(retry: int) -> None:
    await asyncio.sleep(2**retry)
