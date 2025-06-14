import asyncio
import pytest
from app.domain.task import Task
from app.services.ai.summarizer import make_report

class DummyLLM:
    def __init__(self):
        self.prompt = None
    async def chat_complete(self, prompt):
        self.prompt = prompt
        return "ok"

@pytest.mark.asyncio
async def test_make_report_includes_title(monkeypatch):
    task = Task(id='1', title='Write tests', status='done', xp=5)
    async def fake_chat_complete(prompt):
        return prompt
    monkeypatch.setattr('app.services.ai.summarizer.chat_complete', fake_chat_complete)
    md = await make_report([task], 'daily')
    assert 'Write tests' in md

if __name__ == "__main__":
    asyncio.run(test_make_report_includes_title(lambda *a: None))
