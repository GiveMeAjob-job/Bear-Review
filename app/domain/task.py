from datetime import datetime
from pydantic import BaseModel

class Task(BaseModel):
    id: str
    title: str
    due: datetime | None = None
    status: str
    xp: int = 0
