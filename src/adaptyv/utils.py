"""Shared utility functions for Adaptyv Lab SDK."""

from __future__ import annotations

import re
from pathlib import Path


def sanitize_path(path_str: str) -> str:
    """Remove user-specific path prefixes from strings.

    This prevents leaking internal paths (like Claude workspace paths)
    into error messages or tool results when using different LLM backends.

    Args:
        path_str: String that may contain file paths.

    Returns:
        String with home directory replaced by ~ and Claude workspace
        paths normalized to ~/
    """
    home = str(Path.home())
    # Replace home directory with ~
    sanitized = path_str.replace(home, "~")
    # Normalize .claude workspace references (e.g., ~/.claude/projects/uuid/foo -> ~/foo)
    sanitized = re.sub(r"~/.claude/projects/[^/]+/", "~/", sanitized)
    return sanitized
