from pathlib import Path
from typing import Iterable
from jinja2 import Environment, FileSystemLoader
from tiktoken import encoding_for_model

from app.domain.task import Task
from .llm_factory import chat_complete

PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / 'ai' / 'prompts'

async def make_report(tasks: Iterable[Task], period: str) -> str:
    env = Environment(loader=FileSystemLoader(PROMPT_DIR))
    tmpl = env.get_template(f"{period}.jinja2")
    text = tmpl.render(tasks=list(tasks), period=period)
    enc = encoding_for_model("gpt-3.5-turbo")
    if len(enc.encode(text)) > 4000:
        text = enc.decode(enc.encode(text)[:4000])
    return await chat_complete(text)
