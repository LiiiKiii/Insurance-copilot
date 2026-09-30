"""Runtime path helpers for the A1 platform foundation."""

from __future__ import annotations

from pathlib import Path


def _ensure_dir(path: Path) -> Path:
    """Create a directory if necessary and return its path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_dir() -> Path:
    """Return the instance-level runtime data directory."""
    from nanobot.config.loader import get_config_path

    return _ensure_dir(get_config_path().parent)


def get_runtime_subdir(name: str) -> Path:
    """Return a named runtime subdirectory."""
    return _ensure_dir(get_data_dir() / name)


def get_workspace_path(workspace: str | None = None) -> Path:
    """Resolve and ensure the agent workspace directory."""
    path = (
        Path(workspace).expanduser()
        if workspace
        else Path.home() / ".nanobot" / "workspace"
    )
    return _ensure_dir(path)