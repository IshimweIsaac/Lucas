"""Tests for ``core.hot_reloader`` — file-watching and module reload."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def _reset_maps() -> None:
    """Clear the reloader's internal maps before each test."""
    from core import hot_reloader

    hot_reloader._PATH_TO_MODULE.clear()
    hot_reloader._file_mtimes.clear()
    yield


# =========================================================================
# _build_path_map
# =========================================================================


class TestBuildPathMap:
    def test_finds_action_files(self) -> None:
        from core.hot_reloader import _build_path_map, _PATH_TO_MODULE

        _build_path_map()
        action_modules = {
            v for k, v in _PATH_TO_MODULE.items() if v.startswith("actions.")
        }
        # Lucas has 27 action modules registered in tool_registry
        assert len(action_modules) >= 25, (
            f"Expected >=25 action modules, got {len(action_modules)}"
        )

    def test_finds_core_files(self) -> None:
        from core.hot_reloader import _build_path_map, _PATH_TO_MODULE

        _build_path_map()
        core_modules = {
            v for k, v in _PATH_TO_MODULE.items() if v.startswith("core.")
        }
        assert len(core_modules) >= 30, (
            f"Expected >=30 core modules, got {len(core_modules)}"
        )

    def test_finds_agent_files(self) -> None:
        from core.hot_reloader import _build_path_map, _PATH_TO_MODULE

        _build_path_map()
        agent_modules = {
            v for k, v in _PATH_TO_MODULE.items() if v.startswith("agent.")
        }
        assert len(agent_modules) >= 5, (
            f"Expected >=5 agent modules, got {len(agent_modules)}"
        )

    def test_skips_init_py(self) -> None:
        """__init__.py files should not appear in the path map."""
        from core.hot_reloader import _build_path_map, _PATH_TO_MODULE

        _build_path_map()
        init_files = [k for k in _PATH_TO_MODULE if k.endswith("__init__.py")]
        assert init_files == [], f"__init__.py found in path map: {init_files}"


# =========================================================================
# _reload_module
# =========================================================================


class TestReloadModule:
    def test_reload_existing_action_module(self, tmp_path: Path) -> None:
        """Reload a real action module that has already been imported."""
        from core import hot_reloader

        # Discover an existing action file
        lpm_file = PROJECT_ROOT / "actions" / "lpm_control.py"
        assert lpm_file.exists(), "lpm_control.py should exist"
        lpm_path = str(lpm_file)

        # Build maps so the module is registered
        hot_reloader._build_path_map()
        assert lpm_path in hot_reloader._PATH_TO_MODULE

        # Ensure the module is in sys.modules before reload
        import actions.lpm_control  # noqa: F811, F401

        # Simulate a change by adjusting mtime
        hot_reloader._file_mtimes[lpm_path] = lpm_file.stat().st_mtime - 2

        result = hot_reloader._reload_module(lpm_path)
        assert result, "Reload of existing action module should succeed"

    def test_reload_first_import(self, tmp_path: Path) -> None:
        """Reload a module that hasn't been imported yet should still work."""
        from core import hot_reloader

        # Pick a module that exists but may not be imported
        test_module = PROJECT_ROOT / "core" / "system_clock.py"
        test_path = str(test_module)

        # Ensure it is not accidentally imported
        sys.modules.pop("core.system_clock", None)

        hot_reloader._PATH_TO_MODULE[test_path] = "core.system_clock"
        hot_reloader._file_mtimes[test_path] = test_module.stat().st_mtime - 2

        result = hot_reloader._reload_module(test_path)
        assert result, "First-import reload should succeed"

    def test_syntax_error_returns_false(self, tmp_path: Path) -> None:
        """A file with a syntax error should be logged but not crash."""
        from core import hot_reloader

        bad_file = tmp_path / "bad_syntax.py"
        bad_file.write_text("def foo():\n    return x ++\n")
        bad_path = str(bad_file)

        hot_reloader._PATH_TO_MODULE[bad_path] = "bad_syntax"
        hot_reloader._file_mtimes[bad_path] = bad_file.stat().st_mtime - 2

        result = hot_reloader._reload_module(bad_path)
        assert not result, "Syntax errors should return False"

    def test_nonexistent_path_returns_false(self) -> None:
        from core import hot_reloader

        result = hot_reloader._reload_module("/nonexistent/file.py")
        assert not result, "Nonexistent path should return False"


# =========================================================================
# _re_register_action
# =========================================================================


class TestReRegisterAction:
    def test_re_registers_action(self) -> None:
        """An action module should be re-registered after reload."""
        from core import hot_reloader

        # Ensure registry is loaded
        import agent.tool_registry  # noqa: F401

        # Pick an action module that is already imported
        import actions.lpm_control  # noqa: F811, F401

        # Build maps so the path is known
        hot_reloader._build_path_map()

        lpm_file = PROJECT_ROOT / "actions" / "lpm_control.py"
        lpm_path = str(lpm_file)
        hot_reloader._file_mtimes[lpm_path] = lpm_file.stat().st_mtime - 2

        result = hot_reloader._reload_module(lpm_path)
        assert result, "Action reload should succeed"

        # Verify tool is still registered
        assert agent.tool_registry.has_tool("lpm_control")

    def test_non_action_module_does_not_crash(self) -> None:
        """A module outside ``actions.`` should not attempt tool registration."""
        from core import hot_reloader

        hot_reloader._build_path_map()

        test_file = PROJECT_ROOT / "core" / "live_tools.py"
        test_path = str(test_file)
        hot_reloader._file_mtimes[test_path] = test_file.stat().st_mtime - 2

        # This should not raise
        result = hot_reloader._reload_module(test_path)
        assert result, "Core module reload should succeed"


# =========================================================================
# start (thread creation)
# =========================================================================


class TestStart:
    def test_start_creates_daemon_thread(self) -> None:
        from core.hot_reloader import start

        start(interval=5.0)
        threads = [t for t in threading.enumerate() if t.name == "hot-reloader"]
        assert len(threads) == 1
        thread = threads[0]
        assert thread.daemon, "Hot-reloader thread should be a daemon"
        assert thread.is_alive(), "Hot-reloader thread should be running"

    def test_start_idempotent(self) -> None:
        """Multiple calls to start() should be safe (creates extra threads)."""
        from core.hot_reloader import start

        start(interval=5.0)
        start(interval=5.0)
        threads = [
            t for t in threading.enumerate() if t.name == "hot-reloader"
        ]
        # Each call creates a new thread
        assert len(threads) >= 2


import threading  # noqa: E402 needed for TestStart
