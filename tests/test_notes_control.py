"""Tests for the Lucas Notes system (notes_core + notes_control)."""

from __future__ import annotations

import pytest

from core import notes_core as nc
from actions.notes_control import notes_control, _dispatch


# ── Fixtures ──


@pytest.fixture(autouse=True)
def notes_dir(tmp_path: pytest.Testdir, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the notes JSON directory to a temp path for every test."""
    d = tmp_path / "notes"
    monkeypatch.setattr(nc, "_NOTES_DIR", d)
    monkeypatch.setattr(nc, "_NOTES_FILE", d / "notes.json")
    monkeypatch.setattr(nc, "_NOTEBOOKS_FILE", d / "notebooks.json")


# ═══════════════════════════════════════════════════════════════
# NOTEBOOK TESTS
# ═══════════════════════════════════════════════════════════════


class TestNotebooks:
    """CRUD and edge-case tests for notebooks."""

    def test_create_notebook_returns_message(self) -> None:
        result = nc.create_notebook("Work Notes")
        assert "Notebook created" in result
        assert "Work Notes" in result

    def test_create_notebook_with_description(self) -> None:
        result = nc.create_notebook("Journal", "Personal diary")
        assert "Journal" in result

    def test_list_notebooks_empty(self) -> None:
        result = nc.list_notebooks()
        assert "No notebooks" in result

    def test_list_notebooks_after_creation(self) -> None:
        nc.create_notebook("First")
        nc.create_notebook("Second")
        result = nc.list_notebooks()
        assert "Notebooks:" in result
        assert "First" in result
        assert "Second" in result
        assert "nb-1" in result
        assert "nb-2" in result

    def test_delete_notebook_existing(self) -> None:
        nc.create_notebook("To Delete")
        result = nc.delete_notebook("nb-1")
        assert "Notebook deleted" in result
        assert nc.list_notebooks() == "No notebooks. Create one with create_notebook."

    def test_delete_notebook_nonexistent_returns_error(self) -> None:
        result = nc.delete_notebook("nb-999")
        assert "Notebook not found" in result

    def test_delete_notebook_preserves_others(self) -> None:
        nc.create_notebook("Keep")
        nc.create_notebook("Remove")
        nc.delete_notebook("nb-1")
        result = nc.list_notebooks()
        assert "Remove" in result
        assert "Keep" not in result

    def test_create_multiple_notebooks_increments_id(self) -> None:
        ids = []
        for i in range(5):
            result = nc.create_notebook(f"NB {i}")
            ids.append(result)
        for i in range(5):
            assert f"nb-{i + 1}" in ids[i]


# ═══════════════════════════════════════════════════════════════
# NOTE TESTS
# ═══════════════════════════════════════════════════════════════


class TestNotes:
    """CRUD and edge-case tests for notes."""

    def test_create_note_returns_message(self) -> None:
        result = nc.create_note("Shopping List", "Milk, eggs")
        assert "Note created" in result
        assert "Shopping List" in result

    def test_create_note_empty_content(self) -> None:
        result = nc.create_note("Empty Note")
        assert "Note created" in result

    def test_create_note_with_notebook(self) -> None:
        nc.create_notebook("Work")
        result = nc.create_note("Meeting Notes", "Discuss Q3", notebook_id="nb-1")
        assert "Note created" in result

    def test_list_notes_empty(self) -> None:
        result = nc.list_notes()
        assert "No notes found" in result

    def test_list_notes_after_creation(self) -> None:
        nc.create_note("Note A", "Content A")
        nc.create_note("Note B", "Content B")
        result = nc.list_notes()
        assert "Notes:" in result
        assert "Note A" in result
        assert "Note B" in result

    def test_list_notes_filtered_by_notebook(self) -> None:
        nc.create_note("General", "stuff")
        nc.create_note("In Notebook", "inside", notebook_id="nb-1")
        result = nc.list_notes(notebook_id="nb-1")
        assert "In Notebook" in result
        assert "General" not in result

    def test_list_notes_empty_when_notebook_has_none(self) -> None:
        result = nc.list_notes(notebook_id="nb-999")
        assert "No notes found" in result

    def test_get_note_existing(self) -> None:
        nc.create_note("My Note", "Some content here")
        result = nc.get_note("note-1")
        assert "# My Note" in result
        assert "Some content here" in result
        assert "Created:" in result

    def test_get_note_empty_content(self) -> None:
        nc.create_note("Blank")
        result = nc.get_note("note-1")
        assert "(empty)" in result

    def test_get_note_nonexistent_returns_error(self) -> None:
        result = nc.get_note("note-999")
        assert "Note not found" in result

    def test_update_note_title(self) -> None:
        nc.create_note("Old Title")
        result = nc.update_note("note-1", title="New Title")
        assert "Note updated" in result
        assert "New Title" in result
        note = nc.get_note("note-1")
        assert "New Title" in note

    def test_update_note_content(self) -> None:
        nc.create_note("Note", "Old content")
        nc.update_note("note-1", content="New content")
        note = nc.get_note("note-1")
        assert "New content" in note
        assert "Old content" not in note

    def test_update_note_title_and_content(self) -> None:
        nc.create_note("Original", "Original body")
        nc.update_note("note-1", title="Changed", content="Changed body")
        note = nc.get_note("note-1")
        assert "Changed" in note
        assert "Changed body" in note

    def test_update_note_nonexistent_returns_error(self) -> None:
        result = nc.update_note("note-999", title="Anything")
        assert "Note not found" in result

    def test_update_note_preserves_unchanged_fields(self) -> None:
        nc.create_note("Title", "Body content")
        nc.update_note("note-1", title="New Title Only")
        note = nc.get_note("note-1")
        assert "Body content" in note

    def test_delete_note_existing(self) -> None:
        nc.create_note("Delete Me")
        result = nc.delete_note("note-1")
        assert "Note deleted" in result
        assert nc.list_notes() == "No notes found."

    def test_delete_note_nonexistent_returns_error(self) -> None:
        result = nc.delete_note("note-999")
        assert "Note not found" in result

    def test_delete_note_preserves_others(self) -> None:
        nc.create_note("Keep")
        nc.create_note("Remove")
        nc.delete_note("note-2")
        result = nc.list_notes()
        assert "Keep" in result
        assert "Remove" not in result

    def test_multiple_notes_increments_id(self) -> None:
        for i in range(5):
            nc.create_note(f"N{i}")
        for i in range(5):
            note = nc.get_note(f"note-{i + 1}")
            assert f"N{i}" in note


# ═══════════════════════════════════════════════════════════════
# SEARCH TESTS
# ═══════════════════════════════════════════════════════════════


class TestSearch:
    """Search functionality tests."""

    def test_search_by_title(self) -> None:
        nc.create_note("Meeting Notes", "Discuss roadmap")
        result = nc.search_notes("Meeting")
        assert "Meeting Notes" in result

    def test_search_by_content(self) -> None:
        nc.create_note("Random", "Important keyword here")
        result = nc.search_notes("keyword")
        assert "Random" in result

    def test_search_case_insensitive(self) -> None:
        nc.create_note("CAPS TITLE", "some content")
        result = nc.search_notes("caps")
        assert "CAPS TITLE" in result

    def test_search_partial_match_title(self) -> None:
        nc.create_note("My Long Note Title", "")
        result = nc.search_notes("Long Note")
        assert "My Long Note Title" in result

    def test_search_no_match_returns_message(self) -> None:
        nc.create_note("Existing", "stuff")
        result = nc.search_notes("nonexistent")
        assert "No notes matching" in result

    def test_search_matches_multiple(self) -> None:
        nc.create_note("Python Notes", "Learning python")
        nc.create_note("Python Projects", "Working on python apps")
        nc.create_note("Other", "Something else")
        result = nc.search_notes("Python")
        assert "Python Notes" in result
        assert "Python Projects" in result
        assert "Other" not in result


# ═══════════════════════════════════════════════════════════════
# STATS TESTS
# ═══════════════════════════════════════════════════════════════


class TestStats:
    """Statistics and edge-case tests."""

    def test_notes_stats_empty(self) -> None:
        result = nc.notes_stats()
        assert "Notes: 0 in 0 notebooks" in result

    def test_notes_stats_with_data(self) -> None:
        nc.create_notebook("NB1")
        nc.create_notebook("NB2")
        nc.create_note("Note 1")
        nc.create_note("Note 2")
        nc.create_note("Note 3")
        result = nc.notes_stats()
        assert "Notes: 3" in result
        assert "2 notebooks" in result


# ═══════════════════════════════════════════════════════════════
# NOTES_CONTROL ACTION DISPATCH TESTS
# ═══════════════════════════════════════════════════════════════


class TestNotesControlDispatch:
    """Tests for the notes_control action module dispatch."""

    def test_unknown_action_returns_error(self) -> None:
        result = notes_control({"action": "fly_to_moon"})
        assert "Unknown action" in result

    def test_missing_action_returns_error(self) -> None:
        result = notes_control({})
        assert "Missing required parameter" in result

    def test_action_create_notebook(self) -> None:
        result = notes_control({"action": "create_notebook", "name": "Test"})
        assert "Notebook created" in result

    def test_action_list_notebooks(self) -> None:
        notes_control({"action": "create_notebook", "name": "NB"})
        result = notes_control({"action": "list_notebooks"})
        assert "Notebooks:" in result

    def test_action_create_note(self) -> None:
        result = notes_control(
            {
                "action": "create_note",
                "title": "Test Note",
                "content": "Hello world",
            }
        )
        assert "Note created" in result

    def test_action_list_notes(self) -> None:
        notes_control({"action": "create_note", "title": "A"})
        result = notes_control({"action": "list_notes"})
        assert "Notes:" in result

    def test_action_get_note(self) -> None:
        notes_control({"action": "create_note", "title": "View", "content": "Details"})
        result = notes_control({"action": "get_note", "note_id": "note-1"})
        assert "# View" in result

    def test_action_update_note(self) -> None:
        notes_control({"action": "create_note", "title": "Old"})
        result = notes_control(
            {
                "action": "update_note",
                "note_id": "note-1",
                "title": "New",
            }
        )
        assert "Note updated" in result

    def test_action_delete_note(self) -> None:
        notes_control({"action": "create_note", "title": "Gone"})
        result = notes_control({"action": "delete_note", "note_id": "note-1"})
        assert "Note deleted" in result

    def test_action_search_notes(self) -> None:
        notes_control(
            {"action": "create_note", "title": "Find Me", "content": "secret"}
        )
        result = notes_control({"action": "search_notes", "query": "secret"})
        assert "Find Me" in result

    def test_action_notes_stats(self) -> None:
        result = notes_control({"action": "notes_stats"})
        assert "Notes:" in result

    def test_action_help(self) -> None:
        result = notes_control({"action": "help"})
        assert "create_notebook" in result
        assert "create_note" in result
        assert "search_notes" in result

    def test_action_whitespace_is_normalized(self) -> None:
        result = notes_control({"action": "  notes_stats  "})
        assert "Notes:" in result


# ═══════════════════════════════════════════════════════════════
# _dispatch DIRECT TESTS
# ═══════════════════════════════════════════════════════════════


class TestDispatchFunction:
    """Direct unit tests of the _dispatch helper."""

    def test_dispatch_nonexistent_action(self) -> None:
        result = _dispatch("invalid_action", {})
        assert "Unknown action" in result

    def test_dispatch_help(self) -> None:
        result = _dispatch("help", {})
        assert "create_notebook" in result
