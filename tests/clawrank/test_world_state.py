import pytest
from unittest.mock import patch, MagicMock


def test_collect_returns_dict():
    from scripts.clawrank.scotty.world_state import collect_brain_state
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.side_effect = [
        [("transcript_video", 359)],       # doc counts
        [("Concept", 6), ("Product", 5)],  # entity counts
    ]
    mock_cursor.fetchone.return_value = (3,)  # cannibalization count
    with patch("scripts.clawrank.scotty.world_state._get_connection", return_value=mock_conn):
        state = collect_brain_state()
    assert isinstance(state, dict)
    assert "total_docs" in state
    assert state["total_docs"] == 359


def test_state_has_expected_keys():
    from scripts.clawrank.scotty.world_state import collect_brain_state
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.side_effect = [
        [("transcript_video", 359), ("transcript_section", 428)],
        [("Concept", 6), ("Product", 5)],
    ]
    mock_cursor.fetchone.return_value = (3,)
    with patch("scripts.clawrank.scotty.world_state._get_connection", return_value=mock_conn):
        state = collect_brain_state()
    assert "by_type" in state
    assert "entity_counts" in state
    assert "cannibalization_count" in state
    assert "articles_by_pillar" in state
