import os
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, RichLog, Static
from textual.containers import Horizontal, Vertical, Container
from rich.syntax import Syntax
from textual.binding import Binding

from parser import parse_snapshot, Snapshot
from debug import get_logger
from version import __version__

class BrowserDataTable(DataTable):
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

class RepoBrowserApp(App):
    TITLE = "ConfigAnalyzer"
    SUB_TITLE = f"v{__version__} - Device Browser"
    """Simple repository browser.

    - Lists folders (excluding any named 'history').
    - Lists .cfg files as devices in the current folder.
    - Shows user (author) and timestamp if available.
    - Previews device configuration on selection.
    - Press 'o' (Open) on a device to exit and return the device name.
    - Enter to enter a folder; Backspace to go up.
    """

    CSS = """
    #left { width: 48%; }
    #right { width: 52%; border-left: solid steelblue; }
    #right:focus-within { border-left: thick yellow; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("enter", "enter_selected", "Enter/Open"),
        Binding("right", "enter_selected", "Enter/Open"),
        Binding("backspace", "go_up", "Up"),
        Binding("left", "go_up", "Up"),
        Binding("l", "toggle_layout", "Toggle Layout"),
        Binding("home", "cursor_home", "First"),
        Binding("end", "cursor_end", "Last"),
    ]

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

    def compose(self) -> ComposeResult:
        yield Header()
        self.table = BrowserDataTable(id="left")
        self.table.cursor_type = "row"
        self.preview = RichLog(id="right", wrap=True, highlight=False, auto_scroll=self.scroll_to_end)
        self.main_panel = Container(id="browser-main")
        yield self.main_panel
        yield Static("Tips: Enter=open, Backspace=up, L=layout, Home/End=jump, Q=quit", id="tips")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_table()
        if self.start_path and os.path.isdir(self.start_path):
            self.current_path = self.start_path
        self._apply_layout()
        self._load_directory(self.current_path)
        self.logr.debug("mounted at %s", self.current_path)
        self.table.focus()

    def _apply_layout(self) -> None:
        # Clear and mount orientation container
        try:
            for child in list(self.main_panel.children):
                child.remove()
        except Exception:
            pass
        if not hasattr(self, 'layout'):
            self.layout = 'right'
        if self.layout in ('right', 'left'):
            ordered = (self.preview, self.table) if self.layout == 'left' else (self.table, self.preview)
            container = Horizontal(*ordered)
        else:
            ordered = (self.preview, self.table) if self.layout == 'top' else (self.table, self.preview)
            container = Container(Vertical(*ordered))
        self.main_panel.mount(container)

    def _setup_table(self) -> None:
        t = self.table
        # Clear entirely for broader Textual compatibility, then rebuild columns
        t.clear()
        t.add_column("Type", width=8)
        t.add_column("Name")
        t.add_column("User", width=16)
        t.add_column("Timestamp")
        self._row_keys: List[str] = []

    def _load_directory(self, path: str) -> None:
        self.logr.debug("load_directory: %s", path)
        self.current_path = path
        t = self.table
        # Clear and rebuild columns to avoid clear(rows=...) incompatibility
        t.clear()
        self._setup_table()
        self._row_keys = []
        self.preview.clear()

        # Add parent '..' if not at repo root
        if os.path.abspath(path) != os.path.abspath(self.repo_path):
            t.add_row("..", "..", "", "")
            self._row_keys.append("..")

        # List directories (excluding 'history')
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

        for d in dirs:
            t.add_row("dir", d, "", "")
            self._row_keys.append(os.path.join(path, d))

        for f in cfgs:
            full = os.path.join(path, f)
            snap = parse_snapshot(full)
            author = snap.author if snap else ""
            ts = str(snap.timestamp) if snap else ""
            t.add_row("dev", f, author, ts)
            self._row_keys.append(full)

        # Move cursor to first row or highlight the provided file/dir
        if t.row_count:
            if self._start_highlight_file:
                try:
                    idx = self._row_keys.index(self._start_highlight_file)
                    t.cursor_coordinate = (idx, 0)
                except ValueError:
                    t.cursor_coordinate = (0, 0)
                finally:
                    self._start_highlight_file = None
            elif self._highlight_dir_name:
                try:
                    target = os.path.join(path, self._highlight_dir_name)
                    idx = self._row_keys.index(target)
                    t.cursor_coordinate = (idx, 0)
                except ValueError:
                    t.cursor_coordinate = (0, 0)
                finally:
                    self._highlight_dir_name = None
            else:
                t.cursor_coordinate = (0, 0)
        self.logr.debug("load_directory: rows=%s", t.row_count)

    def _selected_row_key(self) -> Optional[str]:
        row = self.table.cursor_row
        if row is None or row < 0 or row >= len(self._row_keys):
            return None
        return self._row_keys[row]

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:  # type: ignore
        # Update preview when selection changes
        key = self._selected_row_key()
        self.logr.debug("row_highlighted: %s", key)
        if not key:
            return
        # If device, preview content; if folder, show hint
        if key == ".." or os.path.isdir(key):
            self.preview.clear()
            self.preview.write(f"Path: {self.current_path}\nEnter to navigate. Press Q to quit.")
        else:
            snap = parse_snapshot(key)
            self.preview.clear()
            if snap:
                try:
                    self.preview.write(Syntax(snap.content_body, "ini", word_wrap=True))
                except Exception:
                    self.preview.write(snap.content_body)
            else:
                try:
                    with open(key, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                        try:
                            self.preview.write(Syntax(content, "ini", word_wrap=True))
                        except Exception:
                            self.preview.write(content)
                except OSError as e:
                    self.preview.write(f"[red]Error reading file:[/red] {e}")

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
        self._apply_layout()

    # 'o' binding removed; Enter handles both folders and device open





