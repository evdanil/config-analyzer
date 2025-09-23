import os
from typing import Dict, List, Optional, Tuple

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, RichLog, Static
from textual.containers import Horizontal, Vertical, Container
from rich.syntax import Syntax
from textual.binding import Binding
from textual import events

from .parser import parse_snapshot, parse_snapshot_meta
from .formatting import format_timestamp
from .filter_mixin import FilterMixin
from .keymap import browser_bindings
from .tips import browser_tips
from .debug import get_logger
from .version import __version__

class BrowserDataTable(DataTable):
    BINDINGS = [
        Binding("home", "goto_first_row", "First", show=False),
        Binding("end", "goto_last_row", "Last", show=False),
        Binding("backspace", "filter_backspace", "", show=False),
        Binding("ctrl+h", "filter_backspace", "", show=False),
        Binding("left", "go_up", "Up", show=True),
        Binding("alt+up", "go_up", "Up", show=False),
        Binding("right", "enter_selected", "Open", show=True),
    ]
    
    def action_goto_first_row(self) -> None:
        try:
            if self.row_count:
                self.cursor_coordinate = (0, 0)
                self._notify_viewport_change()
        except Exception:
            pass
        
    def action_goto_last_row(self) -> None:
        try:
            rc = self.row_count
            if rc:
                self.cursor_coordinate = (rc - 1, 0)
                self._notify_viewport_change()
        except Exception:
            pass

    def _notify_viewport_change(self) -> None:
        try:
            hydrate = getattr(self.app, "_hydrate_viewport", None)
            if hydrate:
                center = getattr(self, "cursor_row", 0) or 0
                hydrate(center_row=center)
        except Exception:
            pass

    async def on_event(self, event: events.Event) -> Optional[bool]:  # type: ignore[override]
        try:
            handled = await super().on_event(event)
        except Exception:
            return None
        scroll_types = tuple(
            t
            for t in (
                getattr(events, "MouseScrollUp", None),
                getattr(events, "MouseScrollDown", None),
                getattr(events, "MouseScrollLeft", None),
                getattr(events, "MouseScrollRight", None),
            )
            if t is not None
        )
        if scroll_types and isinstance(event, scroll_types):
            self._notify_viewport_change()
        return handled

    def on_key(self, event: events.Key) -> None:  # type: ignore
        """Delegate filter keys to the App-level mixin; consume if handled.

        Handling at the widget level ensures Backspace works reliably
        since Textual delivers keys to the focused widget first.
        """
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
        self._notify_viewport_change()

    def action_filter_backspace(self) -> None:
        try:
            fb = getattr(self.app, "filter_backspace", None)
            if fb:
                fb()
        except Exception:
            pass

    def action_go_up(self) -> None:
        try:
            self.app.action_go_up()  # type: ignore[attr-defined]
        except Exception:
            pass

    def action_enter_selected(self) -> None:
        try:
            self.app.action_enter_selected()  # type: ignore[attr-defined]
        except Exception:
            pass

class RepoBrowserApp(FilterMixin, App):
    TITLE = "ConfigAnalyzer"
    SUB_TITLE = f"v{__version__} - Device Browser"
    """Simple repository browser.

    - Lists folders (excluding any named 'history').
    - Lists .cfg files as devices in the current folder.
    - Shows user (author) and timestamp if available.
    - Previews device configuration on selection.
    - Enter to open; Left/Alt+Up to go up.
    """

    CSS = """
    /* Default split for horizontal layouts */
    #left { width: 48%; }
    #right { width: 52%; }

    /* Borders indicate split orientation */
    .layout-right #right { border-left: solid steelblue; }
    .layout-right #right:focus-within { border-left: thick yellow; }
    .layout-left #right { border-right: solid steelblue; }
    .layout-left #right:focus-within { border-right: thick yellow; }
    .layout-bottom #right { border-top: solid steelblue; }
    .layout-bottom #right:focus-within { border-top: thick yellow; }
    .layout-top #right { border-bottom: solid steelblue; }
    .layout-top #right:focus-within { border-bottom: thick yellow; }

    /* Ensure vertical layouts split available height evenly and scroll within panes. */
    .layout-bottom #left { height: 1fr; overflow: hidden; }
    .layout-bottom #right { height: 1fr; overflow: hidden; }
    .layout-top #left { height: 1fr; overflow: hidden; }
    .layout-top #right { height: 1fr; overflow: hidden; }

    /* Ensure main panel expands to fill space so vertical split uses full height */
    #browser-main { height: 1fr; }
    """

    BINDINGS = browser_bindings()

    def __init__(self, repo_path: str, scroll_to_end: bool = False, start_path: Optional[str] = None, start_layout: Optional[str] = None, history_dir: str = 'history'):
        super().__init__()
        self.logr = get_logger("browser")
        self.repo_path = os.path.abspath(repo_path)
        self.current_path = self.repo_path
        self.selected_device_name: Optional[str] = None
        self.scroll_to_end = scroll_to_end
        self.start_path = start_path
        self.layout = start_layout or 'right'
        self.history_dir_l = history_dir.lower()
        self._start_highlight_file: Optional[str] = None
        if self.start_path and os.path.isfile(self.start_path):
            self._start_highlight_file = os.path.abspath(self.start_path)
            self.start_path = os.path.dirname(self._start_highlight_file)
        # Track last directory to highlight when going up
        self._highlight_dir_name: Optional[str] = None
        # Metadata cache for files in current directory (path -> (author, ts_str))
        self._meta_cache: Dict[str, Tuple[str, str]] = {}
        self._pending_cursor_key: Optional[str] = None
        self._row_keys: List[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        # Placeholders; actual widgets are built in _apply_layout
        self.table = BrowserDataTable(id="left")
        self.table.cursor_type = "row"
        self.preview = RichLog(id="right", wrap=True, highlight=False, auto_scroll=self.scroll_to_end)
        self.main_panel = Container(id="browser-main")
        yield self.main_panel
        # Tips/footer text is updated dynamically to show filter
        self.tips = Static("", id="tips")
        yield self.tips
        yield Footer()

    def on_mount(self) -> None:
        self._setup_table()
        if self.start_path and os.path.isdir(self.start_path):
            self.current_path = self.start_path
        self._apply_layout()
        self._filter_text: str = ""
        self._all_entries: List[str] = []  # backing store of paths for current directory
        self._load_directory(self.current_path)
        self.logr.debug("mounted at %s", self.current_path)

        def _focus_table() -> None:
            try:
                self.table.focus()
            except Exception:
                pass

        try:
            self.call_after_refresh(_focus_table)
        except Exception:
            _focus_table()

    def _apply_layout(self) -> None:
        """Rebuild widgets and mount according to current layout.

        Recreating widgets avoids Textual reparenting quirks that can drop
        content render state when switching containers immediately after start.
        """
        try:
            for child in list(self.main_panel.children):
                child.remove()
        except Exception:
            pass

        # Fresh widgets each time
        self.preview = RichLog(id="right", wrap=True, highlight=False, auto_scroll=self.scroll_to_end)
        self.table = BrowserDataTable(id="left")
        self.table.cursor_type = "row"

        # Orientation
        if self.layout in ("right", "left"):
            ordered = (self.preview, self.table) if self.layout == "left" else (self.table, self.preview)
            container = Horizontal(*ordered, classes=f"layout-{self.layout}")
        else:
            ordered = (self.preview, self.table) if self.layout == "top" else (self.table, self.preview)
            container = Vertical(*ordered, classes=f"layout-{self.layout}")
        self.main_panel.mount(container)

        # Columns for the fresh table
        self._setup_table()
        # Refresh tips line
        self._update_tips()

    def _setup_table(self) -> None:
        t = self.table
        try:
            t.clear(columns=True)
        except TypeError:
            t.clear()
            try:
                t.columns.clear()  # type: ignore[attr-defined]
            except Exception:
                pass
        t.add_column("Type", key="type", width=8)
        t.add_column("Name", key="name")
        t.add_column("User", key="user", width=16)
        t.add_column("Timestamp", key="timestamp")
        self._row_keys = []

    def _load_directory(self, path: str) -> None:
        self.logr.debug("load_directory: %s", path)
        self._filter_text = ""
        self.current_path = path
        try:
            self.table.clear()
        except Exception:
            pass
        self.preview.clear()

        try:
            entries = sorted(os.listdir(path), key=str.lower)
        except OSError as e:
            self.preview.write(f"[red]Error reading directory:[/red] {e}")
            return

        dirs: List[str] = []
        cfgs: List[str] = []
        for name in entries:
            full = os.path.join(path, name)
            if os.path.isdir(full):
                if name.lower() == self.history_dir_l:
                    continue
                dirs.append(name)
            elif os.path.isfile(full) and name.lower().endswith(".cfg"):
                cfgs.append(name)

        self._all_entries = []
        for d in dirs:
            self._all_entries.append(os.path.join(path, d))
        for f in cfgs:
            self._all_entries.append(os.path.join(path, f))

        pending_key: Optional[str] = None
        if self._start_highlight_file:
            pending_key = self._start_highlight_file
        elif self._highlight_dir_name:
            pending_key = os.path.join(path, self._highlight_dir_name)

        self._pending_cursor_key = pending_key
        self._render_entries()

        self._start_highlight_file = None
        self._highlight_dir_name = None

    def _update_preview(self, key: str) -> None:
        """Populate the right pane for a given key (file or directory)."""
        # If device, preview content; if folder, show hint
        if key == ".." or os.path.isdir(key):
            self.preview.clear()
            self.preview.write(f"Path: {self.current_path}\nEnter to navigate. Press Q to quit.")
            return
        snap = parse_snapshot(key)
        self.preview.clear()
        if snap:
            try:
                self.preview.write(Syntax(snap.content_body, "ini", word_wrap=True))
            except Exception:
                self.preview.write(snap.content_body)
            return
        try:
            with open(key, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                try:
                    self.preview.write(Syntax(content, "ini", word_wrap=True))
                except Exception:
                    self.preview.write(content)
        except OSError as e:
            self.preview.write(f"[red]Error reading file:[/red] {e}")

    def _selected_row_key(self) -> Optional[str]:
        row = self.table.cursor_row
        if row is None or row < 0 or row >= len(self._row_keys):
            return None
        return self._row_keys[row]

    # -------- Filtering / Quick Search --------
    def _update_tips(self) -> None:
        filter_hint = self.get_filter_hint()
        self.tips.update(browser_tips(filter_hint))

    def _render_entries(self) -> None:
        """Render current directory entries honoring the active filter while minimizing metadata reads."""
        previous_key = self._selected_row_key()
        if self._pending_cursor_key:
            selection_candidate = self._pending_cursor_key
            self._pending_cursor_key = None
        else:
            selection_candidate = previous_key

        ft = (self._filter_text or "").lower()
        at_repo_root = os.path.abspath(self.current_path) == os.path.abspath(self.repo_path)

        self._setup_table()

        if not ft and not at_repo_root:
            self.table.add_row("..", "..", "", "", key="..")
            self._row_keys.append("..")

        filtered: List[str] = []
        if ft:
            for full in self._all_entries:
                name = os.path.basename(full)
                if ft in name.lower():
                    filtered.append(full)
                    continue
                if os.path.isdir(full):
                    continue
                author, ts, _ = self._get_metadata(full, eager=True)
                if ft in author.lower() or ft in ts.lower():
                    filtered.append(full)
        else:
            filtered = list(self._all_entries)

        visible_limit = self._visible_limit()
        tail_start = max(0, len(filtered) - visible_limit)
        selection_index: Optional[int] = None
        if selection_candidate and selection_candidate in filtered:
            try:
                selection_index = filtered.index(selection_candidate)
            except ValueError:
                selection_index = None

        for idx, full in enumerate(filtered):
            base = os.path.basename(full)
            if os.path.isdir(full):
                self.table.add_row("dir", base, "", "", key=full)
            else:
                eager = (
                    idx < visible_limit
                    or idx >= tail_start
                    or (selection_candidate and full == selection_candidate)
                )
                if selection_index is not None:
                    if abs(idx - selection_index) <= visible_limit:
                        eager = True
                author, ts, ready = self._get_metadata(full, eager=eager)
                self.table.add_row("dev", base, author, ts, key=full)
                if not ready and eager:
                    self._pending_cursor_key = full
            self._row_keys.append(full)

        self._update_tips()

        row_index: Optional[int] = None
        if selection_candidate and selection_candidate in self._row_keys:
            target_key = selection_candidate
        elif self._row_keys:
            first_index = 0
            if self._row_keys[0] == ".." and len(self._row_keys) > 1:
                first_index = 1
            target_key = self._row_keys[first_index]
        else:
            target_key = None

        if target_key:
            try:
                row_index = self._row_keys.index(target_key)
                self.table.cursor_coordinate = (row_index, 0)
            except Exception:
                pass

        try:
            current_cursor = self.table.cursor_row or 0
        except Exception:
            current_cursor = 0
        center_row = row_index if row_index is not None else current_cursor
        self._hydrate_viewport(center_row=center_row, buffer=max(visible_limit // 2, 0))

        key = self._selected_row_key()
        if key:
            self._update_preview(key)

        self.logr.debug("render_entries: rows=%s filter='%s'", self.table.row_count, ft)

    def _get_metadata(self, path: str, eager: bool) -> Tuple[str, str, bool]:
        if path in ("..",):
            return "", "", True
        if os.path.isdir(path):
            return "", "", True
        cached = self._meta_cache.get(path)
        if cached:
            return cached[0], cached[1], True
        if not os.path.isfile(path):
            return "", "", True
        if not eager:
            return "...", "...", False
        author, ts = self._load_metadata(path)
        return author, ts, True

    def _load_metadata(self, path: str) -> Tuple[str, str]:
        try:
            snap = parse_snapshot_meta(path)
        except Exception as exc:
            self.logr.debug("parse_snapshot_meta failed for %s: %s", path, exc)
            snap = None
        author = snap.author if snap else ""
        ts_str = format_timestamp(snap.timestamp) if snap and getattr(snap, "timestamp", None) else ""
        meta = (author, ts_str)
        self._meta_cache[path] = meta
        return meta

    def _visible_limit(self) -> int:
        try:
            size = getattr(self.table, "size", None)
            height = getattr(size, "height", 0) if size else 0
            if height:
                return max(int(height), 50)
        except Exception:
            pass
        return 100
    def _viewport_range(self, center_row: Optional[int] = None, buffer: int = 0) -> range:
        total_rows = len(getattr(self, "_row_keys", []))
        if total_rows <= 0:
            return range(0)
        visible = self._visible_limit()
        window = max(visible, 1)
        if buffer:
            window += max(buffer, 0)
        if center_row is None or center_row < 0:
            try:
                center_row = self.table.cursor_row or 0
            except Exception:
                center_row = 0
        center_row = max(0, min(center_row, total_rows - 1))
        start = max(center_row - window, 0)
        end = min(center_row + window + 1, total_rows)
        return range(start, end)

    def _hydrate_viewport(self, center_row: Optional[int] = None, buffer: int = 0) -> None:
        if not getattr(self, "_row_keys", None):
            return
        indices = self._viewport_range(center_row=center_row, buffer=buffer)
        pending: List[Tuple[str, str, str]] = []
        for idx in indices:
            try:
                key = self._row_keys[idx]
            except IndexError:
                continue
            if key == ".." or os.path.isdir(key) or key in self._meta_cache:
                continue
            author, ts = self._load_metadata(key)
            pending.append((key, author, ts))
        if not pending:
            return
        for key, author, ts in pending:
            try:
                self.table.update_cell(key, "user", author)
                self.table.update_cell(key, "timestamp", ts)
            except Exception:
                self._pending_cursor_key = key
                self._render_entries()
                return

    def _ensure_metadata_for_key(self, key: str) -> bool:
        if key in ("..",):
            return False
        if os.path.isdir(key):
            return False
        if key in self._meta_cache:
            return False
        author, ts = self._load_metadata(key)
        try:
            self.table.update_cell(key, "user", author)
            self.table.update_cell(key, "timestamp", ts)
        except Exception:
            self._pending_cursor_key = key
            self._render_entries()
            return True
        return False

    def on_key(self, event: events.Key) -> None:  # type: ignore
        # Delegate to mixin; consume if handled
        if self.process_filter_key(event, require_table_focus=True):
            try:
                event.stop()
            except Exception:
                pass
            return

    def action_quit(self) -> None:
        """Clear filter first when active; otherwise quit."""
        if self.filter_active():
            self.clear_filter()
            return
        self.exit()

    def action_clear_filter(self) -> None:
        self.clear_filter()

    def _on_filter_changed(self) -> None:
        self._render_entries()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:  # type: ignore
        # Update preview when selection changes
        key = self._selected_row_key()
        self.logr.debug("row_highlighted: %s", key)
        if not key:
            return
        if self._ensure_metadata_for_key(key):
            return
        try:
            cursor_row = self.table.cursor_row or 0
        except Exception:
            cursor_row = 0
        self._hydrate_viewport(center_row=cursor_row, buffer=max(self._visible_limit() // 2, 0))
        self._update_preview(key)

    def action_enter_selected(self) -> None:
        key = self._selected_row_key()
        self.logr.debug("enter_selected: %s", key)
        if not key:
            return
        if key == "..":
            self.action_go_up()
            return
        if os.path.isdir(key):
            self._load_directory(key)
        else:
            # Device file selected -> open history directly
            base = os.path.basename(key)
            if base.lower().endswith(".cfg"):
                self.selected_device_name = os.path.splitext(base)[0]
                self.selected_device_cfg_path = key
                self.exit()

    # Ensure Enter on the DataTable triggers navigation even if the widget handles the key
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:  # type: ignore
        self.action_enter_selected()

    def action_go_up(self) -> None:
        if os.path.abspath(self.current_path) == os.path.abspath(self.repo_path):
            return
        parent = os.path.dirname(self.current_path)
        # Remember current dir name to highlight in parent view
        self._highlight_dir_name = os.path.basename(self.current_path)
        self._load_directory(parent)

    # Snap to first/last row actions
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

    def action_toggle_layout(self) -> None:
        order = ["right", "bottom", "left", "top"]
        try:
            idx = order.index(getattr(self, 'layout', 'right'))
        except ValueError:
            idx = 0
        self.layout = order[(idx + 1) % len(order)]

        # Remember current selection to restore after rebuild
        saved_key = self._selected_row_key()

        def _remount() -> None:
            # Rebuild widgets, then reload directory and restore selection
            self._apply_layout()
            self._load_directory(self.current_path)
            if saved_key and saved_key in getattr(self, '_row_keys', []):
                try:
                    i = self._row_keys.index(saved_key)
                    self.table.cursor_coordinate = (i, 0)
                    self._update_preview(saved_key)
                except Exception:
                    pass
            try:
                self.table.focus()
            except Exception:
                pass

        try:
            self.call_after_refresh(_remount)
        except Exception:
            _remount()