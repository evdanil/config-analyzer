from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, RichLog
from textual.containers import Container, Horizontal, Vertical
from textual.binding import Binding
from textual.reactive import reactive
from parser import Snapshot
from debug import get_logger
from differ import get_diff, get_diff_side_by_side
from rich.text import Text


class DiffViewLog(RichLog):
    BINDINGS = [Binding("space", "page_down", "Page Down", show=False)]


class SelectionDataTable(DataTable):
    BINDINGS = []


class CommitSelectorApp(App):
    DEFAULT_CSS = """
    #table-container, #diff_view {
        background: $surface;
    }

    #table-container {
        overflow: hidden;
    }

    #diff_view {
        visibility: hidden;
        padding: 0 1;
    }

    .layout-right #diff_view { border-left: solid steelblue; }
    .layout-right #diff_view:focus-within { border-left: thick yellow; }
    .layout-left #diff_view { border-right: solid steelblue; }
    .layout-left #diff_view:focus-within { border-right: thick yellow; }
    .layout-bottom #diff_view { border-top: solid steelblue; }
    .layout-bottom #diff_view:focus-within { border-top: thick yellow; }
    .layout-top #diff_view { border-bottom: solid steelblue; }
    .layout-top #diff_view:focus-within { border-bottom: thick yellow; }
    """

    show_hide_diff_key = reactive(False, layout=True)
    show_focus_next_key = reactive(False, layout=True)

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "toggle_row", "Toggle Select"),
        Binding("tab", "focus_next", "Switch Panel", show=show_focus_next_key),
        Binding("escape", "hide_diff", "Back to List", show=show_hide_diff_key),
        Binding("d", "toggle_diff_mode", "Toggle Diff View"),
        Binding("l", "toggle_layout", "Toggle Layout"),
    ]

    def __init__(self, snapshots_data: list[Snapshot], scroll_to_end: bool = False, layout: str = "right"):
        super().__init__()
        self.logr = get_logger("tui")
        self.snapshots_data = snapshots_data
        self.scroll_to_end = scroll_to_end
        self.layout = layout
        self.selected_keys: list[str] = []
        self.ordered_keys: list[str] = []
        self.diff_mode: str = "unified"

    def compose(self) -> ComposeResult:
        yield Header()
        # Persistent widgets
        self.diff_view = DiffViewLog(id="diff_view", auto_scroll=self.scroll_to_end, wrap=True, highlight=True)  # type: ignore[attr-defined]
        self.diff_view.can_focus = False
        self.table = SelectionDataTable(id="commit_table")  # type: ignore[attr-defined]
        self.table_container = Container(self.table, id="table-container")  # type: ignore[attr-defined]
        # Main holder; orientation container will be mounted here
        self.main_panel = Container(id="main-panel")  # type: ignore[attr-defined]
        yield self.main_panel
        yield Footer()

    def on_mount(self) -> None:
        # Build initial layout; _apply_layout() will populate the table
        self.logr.debug("on_mount: building layout=%s", self.layout)
        self._apply_layout()
        # Focus after the first refresh to avoid any focus stealing
        def _focus_table() -> None:
            try:
                self.table.focus()
                self.logr.debug("on_mount: focused table (post-refresh); rows=%s", getattr(self.table, 'row_count', 'n/a'))
            except Exception as e:
                self.logr.exception("on_mount: table.focus failed: %s", e)
        try:
            self.call_after_refresh(_focus_table)
        except Exception:
            _focus_table()
        def _focus_table() -> None:
            try:
                self.table.focus()
                self.logr.debug("on_mount: focused table (post-refresh); rows=%s", getattr(self.table, 'row_count', 'n/a'))
            except Exception as e:
                self.logr.exception("on_mount: table.focus failed: %s", e)
        try:
            self.call_after_refresh(_focus_table)
        except Exception:
            _focus_table()

    def _apply_layout(self) -> None:
        """Rebuild the UI fresh to avoid reparent timing issues."""
        self.logr.debug("apply_layout: start layout=%s (rebuild)", self.layout)
        main = self.main_panel
        try:
            for child in list(main.children):
                child.remove()
        except Exception:
            self.logr.debug("apply_layout: clearing main children ignored")
        self.diff_view = DiffViewLog(id="diff_view", auto_scroll=self.scroll_to_end, wrap=True, highlight=True)
        self.diff_view.styles.visibility = "visible" if self.show_hide_diff_key else "hidden"
        self.diff_view.can_focus = bool(self.show_hide_diff_key)
        self.table = SelectionDataTable(id="commit_table")
        self.table_container = Container(self.table, id="table-container")
        if self.layout in ("right", "left"):
            ordered = (self.diff_view, self.table_container) if self.layout == "left" else (self.table_container, self.diff_view)
            container = Horizontal(*ordered, classes=f"layout-{self.layout}")
        else:
            ordered = (self.diff_view, self.table_container) if self.layout == "top" else (self.table_container, self.diff_view)
            container = Vertical(*ordered, classes=f"layout-{self.layout}")
        main.mount(container)
        self.setup_table()
        try:
            for key in self.selected_keys:
                self.table.update_cell(key, "selected_col", Text("x", style="green"))
        except Exception as e:
            self.logr.debug("apply_layout: reapply selections error: %s", e)
        if self.show_hide_diff_key and len(self.selected_keys) == 2:
            self.show_diff()
        try:
            if self.show_hide_diff_key:
                self.diff_view.focus()
            else:
                self.table.focus()
        except Exception:
            self.logr.debug("apply_layout: focus restore ignored")
    def setup_table(self) -> None:
        self.logr.debug("setup_table: %d snapshots", len(self.snapshots_data))
        table = self.table
        # Ensure we start with a clean model for rebuilds
        try:
            table.clear()
        except Exception:
            pass
        table.cursor_type = "row"
        table.add_column("Sel", key="selected_col", width=3)
        table.add_column("Name", key="name_col")
        table.add_column("Date", key="date_col")
        table.add_column("Author", key="author_col")
        # Rebuild ordered_keys to match current rows
        self.ordered_keys = []
        for snapshot in self.snapshots_data:
            key = snapshot.path  # Use full path as unique key
            self.ordered_keys.append(key)
            table.add_row(
                "",
                snapshot.original_filename,
                str(snapshot.timestamp),
                snapshot.author,
                key=key,
            )
        self.logr.debug("setup_table: rows=%s", getattr(table, 'row_count', 'n/a'))
        try:
            table.focus()
        except Exception:
            self.logr.debug("setup_table: table.focus ignored")
    def show_diff(self) -> None:
        self.show_hide_diff_key = True
        self.show_focus_next_key = True

        path1, path2 = self.selected_keys
        snapshot1 = next(s for s in self.snapshots_data if s.path == path1)
        snapshot2 = next(s for s in self.snapshots_data if s.path == path2)

        if snapshot1.timestamp > snapshot2.timestamp:
            snapshot1, snapshot2 = snapshot2, snapshot1

        if self.diff_mode == "side-by-side":
            renderable = get_diff_side_by_side(snapshot1, snapshot2)
        else:
            renderable = get_diff(snapshot1, snapshot2)

        self.logr.debug("show_diff: mode=%s", self.diff_mode)
        diff_view = self.diff_view
        diff_view.clear()
        diff_view.write(renderable)
        diff_view.styles.visibility = "visible"
        diff_view.can_focus = True
        try:
            diff_view.focus()
        except Exception:
            self.logr.debug("show_diff: diff_view.focus ignored")

    def hide_diff_panel(self) -> None:
        self.logr.debug("hide_diff_panel: hide diff and focus table")
        self.diff_view.styles.visibility = "hidden"
        self.diff_view.can_focus = False
        self.show_hide_diff_key = False
        self.show_focus_next_key = False
        try:
            self.table.focus()
        except Exception:
            self.logr.debug("hide_diff_panel: table.focus ignored")

    def action_hide_diff(self) -> None:
        self.hide_diff_panel()
        table = self.table
        for key in self.selected_keys:
            table.update_cell(key, "selected_col", "")
        self.selected_keys.clear()

    def action_toggle_row(self) -> None:
        table = self.table
        if not table.has_focus:
            self.logr.debug("toggle_row: table not focused; ignoring")
            return
        try:
            row_key = self.ordered_keys[table.cursor_row]
        except IndexError:
            self.logr.debug("toggle_row: cursor out of range")
            return
        if row_key in self.selected_keys:
            self.selected_keys.remove(row_key)
            table.update_cell(row_key, "selected_col", "")
        else:
            if len(self.selected_keys) >= 2:
                oldest_key = self.selected_keys.pop(0)
                table.update_cell(oldest_key, "selected_col", "")
            self.selected_keys.append(row_key)
            table.update_cell(row_key, "selected_col", Text("x", style="green"))
        self.logr.debug("toggle_row: selected_keys=%s", self.selected_keys)
        if len(self.selected_keys) == 2:
            self.show_diff()
        else:
            self.hide_diff_panel()

    def action_toggle_diff_mode(self) -> None:
        self.diff_mode = "side-by-side" if self.diff_mode == "unified" else "unified"
        self.logr.debug("toggle_diff_mode: now %s", self.diff_mode)
        # If two selected and diff visible, re-render
        if len(self.selected_keys) == 2 and self.diff_view.styles.visibility == "visible":
            self.show_diff()

    def action_toggle_layout(self) -> None:
        # Cycle layout order: right -> bottom -> left -> top -> right
        order = ["right", "bottom", "left", "top"]
        try:
            idx = order.index(self.layout)
        except ValueError:
            idx = 0
        old = self.layout
        self.layout = order[(idx + 1) % len(order)]
        self.logr.debug("toggle_layout: %s -> %s", old, self.layout)
        # Detach current parents, then remount after the next refresh tick
        try:
            if self.table_container.parent is not None:
                self.table_container.remove()
        except Exception:
            self.logr.debug("toggle_layout: table_container.remove ignored")
        try:
            if self.diff_view.parent is not None:
                self.diff_view.remove()
        except Exception:
            self.logr.debug("toggle_layout: diff_view.remove ignored")

        def _remount() -> None:
            self.logr.debug("toggle_layout: remount phase (layout=%s)", self.layout)
            self._apply_layout()
            # Keep focus sensible
            try:
                if self.show_hide_diff_key:
                    self.diff_view.focus()
                else:
                    self.table.focus()
            except Exception:
                self.logr.debug("toggle_layout: focus restore ignored")

        try:
            self.call_after_refresh(_remount)
        except Exception:
            _remount()








