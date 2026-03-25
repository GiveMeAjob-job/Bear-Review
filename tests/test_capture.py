import sys

from src.capture import main
from src.config import Config
from src.sqlite_task_store import SQLiteTaskStore


def test_capture_done_command_writes_task(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "tasks.db"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capture",
            "--db-path",
            str(db_path),
            "done",
            "剪完第一条视频",
            "--category",
            "Content",
            "--priority",
            "MIT",
            "--date",
            "2026-03-24",
            "--start",
            "09:30",
            "--minutes",
            "45",
        ],
    )

    main()

    output = capsys.readouterr().out
    tasks = SQLiteTaskStore(Config(task_source="sqlite", sqlite_db_path=str(db_path))).recent_done_tasks(5)

    assert "已记录" in output
    assert tasks[0].title == "剪完第一条视频"
    assert tasks[0].category == "Content"
