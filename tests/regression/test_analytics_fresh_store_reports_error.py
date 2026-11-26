"""Reading a fresh analytics store before its first event reported a database error.

Found by the CP 6.2 tests (Brief 003): the writer creates the schema lazily with the first
event, so on a new installation every report query failed with "no such table: events" and the
UI showed an analytics error instead of an empty day. Reads now create the empty schema.
"""

from __future__ import annotations

from interactive_scrolling.storage.analytics import AnalyticsStore


def test_fresh_store_reads_as_empty_without_error(tmp_path) -> None:
    store = AnalyticsStore(tmp_path / "new" / "analytics.sqlite3")
    stats = store.daily_stats()
    assert stats.gestures_confirmed == 0
    assert store.scroll_intervals() == []
    assert store.action_outcomes() == {}
    assert store.eye_report() is None
    assert store.error is None
    store.close()
