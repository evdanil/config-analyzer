def browser_tips(filter_hint: str = "") -> str:
    """Format tips line for the repository browser view."""
    return (
        "Tips: Enter=open, Left/Alt+Up=up, Ctrl+L=layout, Home/End=jump, Ctrl+Q=quit"
        + (filter_hint or "")
    )


def snapshot_tips(filter_hint: str = "", show_diff_controls: bool = False, show_tab: bool = True) -> str:
    """Format tips line for the snapshot selector view.

    show_diff_controls: include D/H hints only when diff panel is the active focus.
    show_tab: include Tab hint only when switching panels is relevant.
    """
    parts = ["Tips: Enter=select"]
    if show_tab:
        parts.append("Tab=switch")
    parts.extend(["Ctrl+L=layout"])
    if show_diff_controls:
        parts.extend(["D=diff", "H=hide"])
    parts.extend(["Esc=back/hide", "Ctrl+Q=quit"])
    return ", ".join(parts) + (filter_hint or "")
