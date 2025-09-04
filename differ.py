import difflib
from typing import TYPE_CHECKING
from rich.syntax import Syntax

# Use a forward reference to avoid circular import
if TYPE_CHECKING:
    from parser import Snapshot

def get_diff(snapshot1: "Snapshot", snapshot2: "Snapshot") -> Syntax:
    """
    Generates a unified diff between the content of two snapshots and wraps it
    in a ``rich.syntax.Syntax`` object for optional colorization.

    Args:
        snapshot1: The first snapshot object.
        snapshot2: The second snapshot object.

    Returns:
        A ``Syntax`` instance containing the diff output.
    """
    lines1 = snapshot1.content_body.splitlines(keepends=True)
    lines2 = snapshot2.content_body.splitlines(keepends=True)

    diff_lines = difflib.unified_diff(
        lines1,
        lines2,
        fromfile=snapshot1.original_filename,
        tofile=snapshot2.original_filename,
        lineterm="",
    )

    diff_text = "".join(diff_lines)
    return Syntax(diff_text, "diff", line_numbers=True, word_wrap=True)
    