"""
Generic utilities (env checks, tool list formatting).
"""

from __future__ import annotations

import os
import sys
from typing import Any


def format_tools_display(tools: list[Any], exclude: tuple[str, ...] = ()) -> str:
    """
    Format a list of MCP tools as a compact table for display.
    Shows only the tool name and the first line of its description.
    Tools with name in exclude are omitted.

    :param tools: List of tool objects (with .name, .description) or dicts (with "name", "description").
    :param exclude: Tool names to omit from output (e.g. task glue tools).
    """
    def _name(t: Any) -> str:
        if isinstance(t, dict):
            return (t.get("name") or "")
        return (getattr(t, "name", None) or "")

    def _summary(t: Any) -> str:
        raw = ""
        if isinstance(t, dict):
            raw = t.get("description") or ""
        else:
            raw = getattr(t, "description", None) or ""
        # First non-empty line only
        for line in raw.splitlines():
            line = line.strip()
            if line:
                return line
        return ""

    visible = [t for t in tools if _name(t) not in exclude]
    if not visible:
        return "  (none)"

    # Align names for readability
    max_name = max(len(_name(t)) for t in visible)
    lines = []
    for t in visible:
        n = _name(t)
        s = _summary(t)
        lines.append(f"  {n:<{max_name}}  {s}")
    return "\n".join(lines)


def require_env(*var_names: str, hint: str | None = None) -> dict[str, str]:
    """
    Require that the given environment variables are set (non-empty).
    Exits the process with a clear message if any are missing.

    :param var_names: Environment variable names (e.g. "OPENAI_API_KEY", "AGNTID_MCP_URL").
    :param hint: Optional extra line printed before exit (e.g. pip install instructions).
    :returns: Dict of var_name -> value for all required vars (only if all present).
    """
    missing = []
    values: dict[str, str] = {}
    for v in var_names:
        val = os.environ.get(v, "").strip()
        values[v] = val
        if not val:
            missing.append(v)
    if missing:
        print("Missing required environment variables:", ", ".join(missing), file=sys.stderr)
        for v in var_names:
            if v not in missing:
                continue
            print(f"  export {v}=...", file=sys.stderr)
        if hint:
            print(hint, file=sys.stderr)
        sys.exit(1)
    return values
