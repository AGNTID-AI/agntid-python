"""
Rich-formatted display helpers for the AgntID SDK.

Provides polished, coloured terminal output for tool results, denials,
tool lists, and connection status.  Uses the ``rich`` library.

ToolResult and DenialResult are returned by the wrapped client so that
``print(result)`` automatically renders with rich — no extra call needed.
They also behave like the underlying data (dict access, iteration, etc.)
for programmatic use.
"""

from __future__ import annotations

import io
import json
from typing import Any, Iterator

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich import box

_console = Console(stderr=False)

# ── Theme ────────────────────────────────────────────────────────────

ACCENT = "cyan"
SUCCESS = "green"
DENIED = "red"
WARN = "yellow"
DIM = "dim"
LABEL = "bold white"


# ── Auto-rendering result types ──────────────────────────────────────

class ToolResult(dict):
    """
    Dict subclass returned by the wrapped client on success.
    ``print(result)`` renders a rich table; ``result["key"]`` works normally.
    """

    def __init__(self, data: dict[str, Any], tool_name: str | None = None) -> None:
        super().__init__(data)
        self._tool_name = tool_name

    def __str__(self) -> str:
        buf = io.StringIO()
        c = Console(file=buf, force_terminal=True, width=88)
        _render_dict_to(c, dict(self), self._tool_name)
        return buf.getvalue()

    def __repr__(self) -> str:
        return f"ToolResult({dict.__repr__(self)})"


class ToolResultScalar:
    """
    Wrapper for non-dict results (strings, numbers, lists).
    ``print(result)`` renders a rich panel; ``.value`` holds the raw data.
    """

    def __init__(self, value: Any, tool_name: str | None = None) -> None:
        self.value = value
        self._tool_name = tool_name

    def __str__(self) -> str:
        buf = io.StringIO()
        c = Console(file=buf, force_terminal=True, width=88)
        if isinstance(self.value, list):
            _render_list_to(c, self.value, self._tool_name)
        else:
            title = f"[bold {ACCENT}]{self._tool_name}[/]" if self._tool_name else f"[bold {ACCENT}]Result[/]"
            c.print(Panel(str(self.value), title=title, border_style=SUCCESS, padding=(0, 1)))
        return buf.getvalue()

    def __repr__(self) -> str:
        return f"ToolResultScalar({self.value!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, ToolResultScalar):
            return self.value == other.value
        return self.value == other


class DenialResult:
    """
    Returned by the wrapped client when a tool call is denied by policy.
    ``print(result)`` renders a red denial panel.
    ``.denied`` is True; ``.message`` holds the reason string.
    """

    def __init__(self, message: str, tool_name: str | None = None) -> None:
        self.message = message
        self.denied = True
        self._tool_name = tool_name

    def __str__(self) -> str:
        buf = io.StringIO()
        c = Console(file=buf, force_terminal=True, width=88)
        title = f"[bold {DENIED}]Denied[/]"
        if self._tool_name:
            title += f"  [bold {WARN}]{self._tool_name}[/]"
        c.print(Panel(self.message, title=title, border_style=DENIED, padding=(0, 1)))
        return buf.getvalue()

    def __repr__(self) -> str:
        return f"DenialResult({self.message!r})"

    def __bool__(self) -> bool:
        return False


# ── Rendering helpers ────────────────────────────────────────────────

def _format_value(v: Any) -> str:
    if isinstance(v, dict):
        return json.dumps(v, default=str, indent=2)
    if isinstance(v, list):
        if len(v) <= 5:
            return ", ".join(str(x) for x in v)
        return json.dumps(v, default=str)
    if isinstance(v, bool):
        return f"[{SUCCESS}]true[/]" if v else f"[{DENIED}]false[/]"
    if isinstance(v, (int, float)):
        return f"[bold white]{v}[/]"
    return str(v)


def _render_dict_to(c: Console, data: dict[str, Any], tool_name: str | None) -> None:
    title = f"[bold {ACCENT}]{tool_name}[/]" if tool_name else f"[bold {ACCENT}]Result[/]"
    table = Table(
        show_header=True,
        header_style=f"bold {ACCENT}",
        box=box.ROUNDED,
        title=title,
        title_style="",
        border_style=SUCCESS,
        padding=(0, 1),
    )
    table.add_column("Key", style=LABEL, no_wrap=True)
    table.add_column("Value", style="white")
    for k, v in data.items():
        table.add_row(str(k), _format_value(v))
    c.print(table)


def _render_list_to(c: Console, data: list[Any], tool_name: str | None) -> None:
    label = tool_name or "Result"
    tree = Tree(f"[bold {ACCENT}]{label}[/]")
    for i, item in enumerate(data):
        if isinstance(item, dict):
            branch = tree.add(f"[{DIM}][{i}][/]")
            for k, v in item.items():
                branch.add(f"[{LABEL}]{k}[/]: {_format_value(v)}")
        else:
            tree.add(f"[{DIM}][{i}][/] {_format_value(item)}")
    c.print(tree)


# ── Public print functions (still available for manual use) ──────────

def print_result(result: Any, *, tool_name: str | None = None) -> None:
    """Pretty-print a tool call result."""
    if isinstance(result, (ToolResult, ToolResultScalar, DenialResult)):
        _console.print(str(result), highlight=False, end="")
        return
    if isinstance(result, str) and ("denied" in result.lower() or "failed" in result.lower()):
        print_denial_message(result, tool_name=tool_name)
        return
    title = f"[bold {ACCENT}]{tool_name}[/]" if tool_name else f"[bold {ACCENT}]Result[/]"
    if isinstance(result, dict):
        _render_dict_to(_console, result, tool_name)
    elif isinstance(result, list):
        _render_list_to(_console, result, tool_name)
    else:
        _console.print(Panel(str(result), title=title, border_style=SUCCESS, padding=(0, 1)))


def print_denial(denial: dict[str, Any] | None) -> None:
    """Pretty-print a denial dict (from ``get_last_denial()``)."""
    if denial is None:
        return
    tool = denial.get("tool", "unknown")
    reason = denial.get("reason", "denied")

    content = Text()
    content.append("Tool:   ", style=DIM)
    content.append(tool, style=f"bold {WARN}")
    content.append("\n")
    content.append("Reason: ", style=DIM)
    content.append(reason, style="white")
    if denial.get("policy_name"):
        content.append("\n")
        content.append("Policy: ", style=DIM)
        content.append(denial["policy_name"], style=ACCENT)
    if denial.get("intent_mismatch"):
        content.append("\n")
        content.append("Intent: ", style=DIM)
        content.append(denial["intent_mismatch"], style=WARN)
    if denial.get("denial_step"):
        content.append("\n")
        content.append("Step:   ", style=DIM)
        content.append(denial["denial_step"], style=DIM)

    _console.print(Panel(
        content,
        title=f"[bold {DENIED}]Policy Denied[/]",
        border_style=DENIED,
        padding=(0, 1),
    ))


def print_denial_message(msg: str, *, tool_name: str | None = None) -> None:
    """Print a denial string."""
    title = f"[bold {DENIED}]Denied[/]"
    if tool_name:
        title += f"  [bold {WARN}]{tool_name}[/]"
    _console.print(Panel(msg, title=title, border_style=DENIED, padding=(0, 1)))


def print_tools(tools: list[Any], *, exclude: tuple[str, ...] = ()) -> None:
    """Pretty-print the list of MCP tools as a bordered table."""
    def _name(t: Any) -> str:
        return (t.get("name") if isinstance(t, dict) else getattr(t, "name", None)) or ""

    def _desc(t: Any) -> str:
        raw = (t.get("description") if isinstance(t, dict) else getattr(t, "description", None)) or ""
        for line in raw.splitlines():
            line = line.strip()
            if line:
                return line
        return ""

    visible = [t for t in tools if _name(t) not in exclude]

    table = Table(
        show_header=True,
        header_style=f"bold {ACCENT}",
        box=box.ROUNDED,
        title=f"[bold {ACCENT}]MCP Tools[/]",
        title_style="",
        border_style=ACCENT,
        padding=(0, 1),
    )
    table.add_column("#", style=DIM, width=4, justify="right")
    table.add_column("Tool", style=LABEL, no_wrap=True)
    table.add_column("Description", style="white")

    if not visible:
        table.add_row("", "(none)", "")
    else:
        for i, t in enumerate(visible, 1):
            table.add_row(str(i), _name(t), _desc(t))
    _console.print(table)


def print_connected(url: str, *, tool_count: int | None = None) -> None:
    """Print a connection-success banner."""
    parts = Text()
    parts.append("Connected to ", style=DIM)
    parts.append(url, style=f"bold {ACCENT}")
    if tool_count is not None:
        parts.append(f"  ({tool_count} tools)", style=DIM)
    _console.print(Panel(parts, border_style=SUCCESS, padding=(0, 1)))


def print_task_opened(task_id: str, agent_id: str) -> None:
    """Print task-opened confirmation."""
    parts = Text()
    parts.append("Task: ", style=DIM)
    parts.append(task_id[:16] + "...", style=f"bold {ACCENT}")
    parts.append("  Agent: ", style=DIM)
    parts.append(agent_id, style=LABEL)
    _console.print(parts)


def print_error(msg: str) -> None:
    """Print a generic error message."""
    _console.print(Panel(msg, title=f"[bold {DENIED}]Error[/]", border_style=DENIED, padding=(0, 1)))
