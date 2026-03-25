import json

from src.models import ReviewReport
from src.review_memory import ReviewMemoryStore


def test_memory_store_round_trip(tmp_path):
    path = tmp_path / "memory.json"
    store = ReviewMemoryStore(str(path))
    report = ReviewReport(
        period="daily",
        title="Daily",
        content="今日推进。\n复盘标签：主线推进，执行摩擦，睡眠偏移\n下一轮跟进：上午先做 60 分钟 D333 Quiz",
        preview="日报速览：推进主线",
        stats={"total": 3, "xp": 20, "mit_count": 1},
    )

    store.record_report(report, generated_at="2026-03-24T02:20:00-04:00")
    store.save()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["entries"][0]["tags"] == ["主线推进", "执行摩擦", "睡眠偏移"]
    assert payload["entries"][0]["follow_up"] == "上午先做 60 分钟 D333 Quiz"


def test_memory_store_builds_context_from_history(tmp_path):
    path = tmp_path / "memory.json"
    store = ReviewMemoryStore(str(path))
    store.record_report(
        ReviewReport(
            period="daily",
            title="Daily 1",
            content="复盘标签：主线推进，拖延\n下一轮跟进：先做最难 MIT",
            preview="日报速览：完成 2 项",
            stats={"total": 2, "xp": 10, "mit_count": 1},
        ),
        generated_at="2026-03-22T02:20:00-04:00",
    )
    store.record_report(
        ReviewReport(
            period="daily",
            title="Daily 2",
            content="复盘标签：主线推进，拖延\n下一轮跟进：晚上 11 点前停机",
            preview="日报速览：完成 4 项",
            stats={"total": 4, "xp": 30, "mit_count": 2},
        ),
        generated_at="2026-03-23T02:20:00-04:00",
    )

    context = store.build_context("daily", {"total": 5, "xp": 40, "mit_count": 2})

    assert "最近同周期复盘" in context
    assert "近期高频标签：主线推进, 拖延" in context
    assert "上一次承诺跟进：晚上 11 点前停机" in context


def test_memory_store_round_trip_with_sqlite_backend(tmp_path):
    path = tmp_path / "state.db"
    store = ReviewMemoryStore(str(path))
    store.record_report(
        ReviewReport(
            period="daily",
            title="Daily",
            content="复盘标签：主线推进\n下一轮跟进：先做最难 MIT",
            preview="日报速览：完成 2 项",
            stats={"total": 2, "xp": 10, "mit_count": 1},
        ),
        generated_at="2026-03-24T02:20:00-04:00",
    )
    store.save()

    reloaded = ReviewMemoryStore(str(path))
    context = reloaded.build_context("daily", {"total": 3, "xp": 12, "mit_count": 1})

    assert "最近同周期复盘" in context
    assert "上一次承诺跟进：先做最难 MIT" in context


def test_memory_store_imports_legacy_json_into_sqlite(tmp_path):
    legacy_path = tmp_path / "memory.json"
    legacy_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "period": "daily",
                        "title": "Legacy",
                        "preview": "旧摘要",
                        "generated_at": "2026-03-24T02:20:00-04:00",
                        "stats": {"total": 1},
                        "tags": ["旧标签"],
                        "follow_up": "旧跟进",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = ReviewMemoryStore(str(tmp_path / "state.db"))
    imported = store.maybe_import_json_file(str(legacy_path))
    context = store.build_context("daily", {"total": 1})

    assert imported is True
    assert "旧摘要" in context
