from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, RichLog
from textual.containers import Container, Horizontal, Vertical
from textual.binding import Binding
from textual.reactive import reactive

from .parser import Snapshot
from .debug import get_logger
from .version import __version__
from .differ import get_diff, get_diff_side_by_side
from rich.text import Text
from rich.syntax import Syntax


class DiffViewLog(RichLog):
    BINDINGS = [Binding("space", "page_down", "Page Down", show=False)]


class SelectionDataTable(DataTable):
    BINDINGS = [
        Binding("home", "goto_first_row", "First", show=False),
        Binding("end", "goto_last_row", "Last", show=False),
    ]

    def action_goto_first_row(self) -> None:
        try:
            if self.row_count:
                self.cursor_coordinate = (0, 0)
        except Exception:
            pass

    def action_goto_last_row(self) -> None:
        try:
            rc = self.row_count
            if rc:
                self.cursor_coordinate = (rc - 1, 0)
        except Exception:
            pass


class CommitSelectorApp(App):
    TITLE = "ConfigAnalyzer"
    SUB_TITLE = f"v{__version__} — Snapshot History"

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
        Binding("escape", "hide_diff", "Back / Hide Diff", show=show_hide_diff_key),
        Binding("backspace", "go_back", "Back to Devices"),
        Binding("home", "cursor_home", "First"),
        Binding("end", "cursor_end", "Last"),
        Binding("d", "toggle_diff_mode", "Toggle Diff View"),
        Binding("l", "toggle_layout", "Toggle Layout"),
        Binding("h", "toggle_hide_unchanged", "Hide Unchanged"),
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
        self.hide_unchanged_sbs: bool = False
        self.navigate_back: bool = False

    def compose(self) -> ComposeResult:
        yield Header()
        # Placeholders; actual layout is mounted in _apply_layout
        self.diff_view = DiffViewLog(id="diff_view", auto_scroll=self.scroll_to_end, wrap=True, highlight=True)
        self.diff_view.can_focus = False
        self.table = SelectionDataTable(id="commit_table")
        self.table_container = Container(self.table, id="table-container")
        self.main_panel = Container(id="main-panel")
        yield self.main_panel
        yield Footer()

    def on_mount(self) -> None:
        self.logr.debug("on_mount: layout=%s", self.layout)
        self._apply_layout()

        def _focus_table() -> None:
            try:
                self.table.focus()
                self.logr.debug("on_mount: focused table; rows=%s", getattr(self.table, 'row_count', 'n/a'))
            except Exception as e:
                self.logr.exception("on_mount: table.focus failed: %s", e)

        try:
            self.call_after_refresh(_focus_table)
        except Exception:
            _focus_table()

    def _apply_layout(self) -> None:
        """Rebuild widgets to avoid reparent timing issues on Textual 0.61."""
        self.logr.debug("apply_layout: rebuild layout=%s", self.layout)
        # Clear container
        try:
            for child in list(self.main_panel.children):
                child.remove()
        except Exception:
            pass

        # Fresh widgets each time
        self.diff_view = DiffViewLog(id="diff_view", auto_scroll=self.scroll_to_end, wrap=True, highlight=True)
        if not self.show_hide_diff_key:
            self.diff_view.styles.visibility = "hidden"
            self.diff_view.can_focus = False
        else:
            self.diff_view.styles.visibility = "visible"
            self.diff_view.can_focus = True

        self.table = SelectionDataTable(id="commit_table")
        self.table_container = Container(self.table, id="table-container")

        # Orientation
        if self.layout in ("right", "left"):
            ordered = (self.diff_view, self.table_container) if self.layout == "left" else (self.table_container, self.diff_view)
            container = Horizontal(*ordered, classes=f"layout-{self.layout}")
        else:
            ordered = (self.diff_view, self.table_container) if self.layout == "top" else (self.table_container, self.diff_view)
            container = Vertical(*ordered, classes=f"layout-{self.layout}")
        self.main_panel.mount(container)

        # Populate table and reapply state
        self.setup_table()
        for key in self.selected_keys:
            try:
                self.table.update_cell(key, "selected_col", Text("x", style="green"))
            except Exception:
                pass

        if self.show_hide_diff_key and len(self.selected_keys) == 2:
            self.show_diff()

        # Keep focus on table always; user can Tab to diff
        try:
            self.table.focus()
        except Exception:
            pass

    def setup_table(self) -> None:
        self.logr.debug("setup_table: %d snapshots", len(self.snapshots_data))
        table = self.table
        # Clean model to avoid duplicate columns
        try:
            table.clear()
        except Exception:
            pass
        table.cursor_type = "row"
        table.add_column("Sel", key="selected_col", width=3)
        table.add_column("Name", key="name_col")
        table.add_column("Date", key="date_col")
        table.add_column("Author", key="author_col")
        self.ordered_keys = []
        for snapshot in self.snapshots_data:
            key = snapshot.path
            self.ordered_keys.append(key)
            table.add_row(
                "",
                snapshot.original_filename,
                str(snapshot.timestamp),
                snapshot.author,
                key=key,
            )

    def show_diff(self) -> None:
        self.show_hide_diff_key = True
        self.show_focus_next_key = True

        path1, path2 = self.selected_keys
        snapshot1 = next(s for s in self.snapshots_data if s.path == path1)
        snapshot2 = next(s for s in self.snapshots_data if s.path == path2)
        if snapshot1.timestamp > snapshot2.timestamp:
            snapshot1, snapshot2 = snapshot2, snapshot1

        if self.diff_mode == "side-by-side":
            renderable = get_diff_side_by_side(snapshot1, snapshot2, hide_unchanged=self.hide_unchanged_sbs)
        else:
            renderable = get_diff(snapshot1, snapshot2)

        self.diff_view.clear()
        self.diff_view.write(renderable)
        self.diff_view.styles.visibility = "visible"
        self.diff_view.can_focus = True  # allow Tab focus, but don't take focus now
        # Keep focus on table

    def hide_diff_panel(self) -> None:
        self.logr.debug("hide_diff_panel")
        self.diff_view.styles.visibility = "hidden"
        self.diff_view.can_focus = False
        self.show_hide_diff_key = False
        self.show_focus_next_key = False
        try:
            self.table.focus()
        except Exception:
            pass

    def action_hide_diff(self) -> None:
        # If diff visible, hide and clear selection; otherwise, go back to repo
        if self.diff_view.styles.visibility == "visible":
            self.hide_diff_panel()
            for key in self.selected_keys:
                self.table.update_cell(key, "selected_col", "")
            self.selected_keys.clear()
        else:
            self.action_go_back()

    def action_go_back(self) -> None:
        self.navigate_back = True
        self.exit()

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
        if len(self.selected_keys) == 2:
            self.show_diff()
        elif len(self.selected_keys) == 1:
            # Show single snapshot content with syntax highlighting
            self.show_single()
        else:
            self.hide_diff_panel()

    def show_single(self) -> None:
        try:
            path = self.selected_keys[-1]
        except IndexError:
            return
        try:
            snap = next(s for s in self.snapshots_data if s.path == path)
        except StopIteration:
            return
        self.diff_view.clear()
        try:
            self.diff_view.write(Syntax(snap.content_body, "ini", line_numbers=False, word_wrap=True))
        except Exception:
            self.diff_view.write(snap.content_body)
        self.diff_view.styles.visibility = "visible"
        self.diff_view.can_focus = True

    def action_toggle_diff_mode(self) -> None:
        self.diff_mode = "side-by-side" if self.diff_mode == "unified" else "unified"
        if len(self.selected_keys) == 2 and self.diff_view.styles.visibility == "visible":
            self.show_diff()

    def action_toggle_layout(self) -> None:
        order = ["right", "bottom", "left", "top"]
        try:
            idx = order.index(self.layout)
        except ValueError:
            idx = 0
        self.layout = order[(idx + 1) % len(order)]

        def _remount() -> None:
            self._apply_layout()
            try:
                self.table.focus()
            except Exception:
                pass

        try:
            self.call_after_refresh(_remount)
        except Exception:
            _remount()

    def action_toggle_hide_unchanged(self) -> None:
        self.hide_unchanged_sbs = not self.hide_unchanged_sbs
        if self.diff_mode == "side-by-side" and len(self.selected_keys) == 2 and self.diff_view.styles.visibility == "visible":
            self.show_diff()

    def action_cursor_home(self) -> None:
        try:
            if self.table.row_count:
                self.table.cursor_coordinate = (0, 0)
        except Exception:
            pass

    def action_cursor_end(self) -> None:
        try:
            rc = self.table.row_count
            if rc:
                self.table.cursor_coordinate = (rc - 1, 0)
        except Exception:
            pass
