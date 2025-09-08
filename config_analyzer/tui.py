from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, RichLog, Static
from textual.containers import Container, Horizontal, Vertical
from textual.binding import Binding
from textual.reactive import reactive
from textual import events

from .parser import Snapshot
from .filter_mixin import FilterMixin
from .debug import get_logger
from .version import __version__
from .differ import get_diff, get_diff_side_by_side
from .keymap import snapshot_bindings
from .tips import snapshot_tips
from rich.text import Text
from rich.syntax import Syntax
from .formatting import format_timestamp


class DiffViewLog(RichLog):
    BINDINGS = [
        Binding("space", "page_down", "Page Down", show=False),
        Binding("d", "toggle_diff_mode", "Toggle Diff View"),
        Binding("h", "toggle_hide_unchanged", "Hide Unchanged"),
        Binding("tab", "focus_next_panel", "Switch Panel", show=False),
    ]

    def action_toggle_diff_mode(self) -> None:
        try:
            self.app.action_toggle_diff_mode()  # type: ignore[attr-defined]
        except Exception:
            pass

    def action_toggle_hide_unchanged(self) -> None:
        try:
            self.app.action_toggle_hide_unchanged()  # type: ignore[attr-defined]
        except Exception:
            pass

    def action_focus_next_panel(self) -> None:
        try:
            self.app.action_focus_next()  # type: ignore[attr-defined]
        except Exception:
            pass

    def on_key(self, event: events.Key) -> None:  # type: ignore
        # Ensure Tab always switches panel even if widget defaults intercept
        if event.key == "tab":
            self.action_focus_next_panel()
            try:
                event.stop()
            except Exception:
                pass
            return
        try:
            super().on_key(event)
        except Exception:
            pass


class SelectionDataTable(DataTable):
    BINDINGS = [
        Binding("home", "goto_first_row", "First", show=False),
        Binding("end", "goto_last_row", "Last", show=False),
        Binding("enter", "select_row", "Select", show=False),
        Binding("backspace", "filter_backspace", "", show=False),
        Binding("ctrl+h", "filter_backspace", "", show=False),
        Binding("tab", "focus_next_panel", "Switch Panel", show=False),
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

    def action_select_row(self) -> None:
        """Delegate row selection to the App's selection action."""
        try:
            # Toggle selection at the app level to keep logic DRY
            self.app.action_toggle_row()  # type: ignore[attr-defined]
        except Exception:
            pass

    def action_filter_backspace(self) -> None:
        try:
            fb = getattr(self.app, "filter_backspace", None)
            if fb:
                fb()
        except Exception:
            pass

    def action_focus_next_panel(self) -> None:
        try:
            self.app.action_focus_next()  # type: ignore[attr-defined]
        except Exception:
            pass

    def on_key(self, event: events.Key) -> None:  # type: ignore
        """Delegate filter keys to the App-level mixin; consume if handled.

        Handling at the widget level ensures Backspace/Enter work reliably
        since Textual delivers keys to the focused widget first.
        """
        # Force Tab to switch panel (DataTable may consume it otherwise)
        if event.key == "tab":
            self.action_focus_next_panel()
            try:
                event.stop()
            except Exception:
                pass
            return
        try:
            handler = getattr(self.app, "process_filter_key", None)
            if handler and handler(event, require_table_focus=False):
                try:
                    event.stop()
                except Exception:
                    pass
                return
        except Exception:
            pass
        # Not handled by filter -> allow normal bindings/defaults to run
        try:
            super().on_key(event)
        except Exception:
            pass


class CommitSelectorApp(FilterMixin, App):
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

    #main-panel { height: 1fr; }
    """

    show_hide_diff_key = reactive(False, layout=True)
    show_focus_next_key = reactive(False, layout=True)
    # Dynamic footer hint visibility
    show_select_key = reactive(True)
    show_diff_controls_key = reactive(False)

    BINDINGS = snapshot_bindings(show_hide_diff_key, show_focus_next_key, show_select_key, show_diff_controls_key)

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
        self.tips = Static("", id="tips")
        yield self.tips
        yield Footer()

    def on_mount(self) -> None:
        self.logr.debug("on_mount: layout=%s", self.layout)
        self._apply_layout()
        self._filter_text: str = ""
        # Initialize footer hint flags
        self._update_focus_flags()

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
        self._update_tips()
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
        self._update_focus_flags()

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
        # Render rows honoring any active filter
        self._render_rows()

    def _update_tips(self) -> None:
        filter_hint = self.get_filter_hint()
        show_diff_controls = bool(self.show_diff_controls_key)
        show_tab = True
        self.tips.update(snapshot_tips(filter_hint, show_diff_controls=show_diff_controls, show_tab=show_tab))

    def action_focus_next(self) -> None:
        """Ensure footer hint flags are updated after focus changes."""
        try:
            self.screen.focus_next()
        except Exception:
            pass
        self._update_focus_flags()
        self._update_tips()

    def _update_focus_flags(self) -> None:
        try:
            diff_visible = self.diff_view.styles.visibility == "visible"
        except Exception:
            diff_visible = False
        # Enter hint when table focused
        self.show_select_key = bool(getattr(self.table, "has_focus", False))
        # D/H hints when diff visible and focused
        self.show_diff_controls_key = bool(diff_visible and getattr(self.diff_view, "has_focus", False))

    def _render_rows(self) -> None:
        table = self.table
        try:
            table.clear(columns=False)
        except Exception:
            # If clear with columns arg unsupported, rebuild columns
            table.clear()
            table.add_column("Sel", key="selected_col", width=3)
            table.add_column("Name", key="name_col")
            table.add_column("Date", key="date_col")
            table.add_column("Author", key="author_col")
        self.ordered_keys = []
        ft = (getattr(self, "_filter_text", "") or "").lower()
        for snapshot in self.snapshots_data:
            name = snapshot.original_filename
            author = snapshot.author or ""
            ts_str = str(snapshot.timestamp)
            if ft and not (ft in name.lower() or ft in author.lower() or ft in ts_str.lower()):
                continue
            key = snapshot.path
            self.ordered_keys.append(key)
            table.add_row(
                "x" if key in self.selected_keys else "",
                name,
                format_timestamp(snapshot.timestamp),
                snapshot.author,
                key=key,
            )
        # Reset cursor to first row
        try:
            if table.row_count:
                table.cursor_coordinate = (0, 0)
        except Exception:
            pass
        self._update_tips()

    def on_key(self, event: events.Key) -> None:  # type: ignore
        # Delegate to mixin; consume if handled (only when table focused)
        if self.process_filter_key(event, require_table_focus=True):
            try:
                event.stop()
            except Exception:
                pass
            return

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
        self._update_focus_flags()

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
        self._update_focus_flags()

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
        # Clear filter on leaving the snapshot view
        self.clear_filter()
        self.navigate_back = True
        self.exit()

    def _on_filter_changed(self) -> None:
        self._render_rows()

    def action_quit(self) -> None:
        # Clear filter first when active; else quit
        if getattr(self, "_filter_text", ""):
            self._filter_text = ""
            self._render_rows()
            return
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
