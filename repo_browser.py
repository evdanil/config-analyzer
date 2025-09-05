import os
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, RichLog
from textual.containers import Horizontal
from textual.binding import Binding

from parser import parse_snapshot, Snapshot
from debug import get_logger


class RepoBrowserApp(App):
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
        Binding("enter", "enter_selected", "Enter"),
        Binding("right", "enter_selected", "Enter"),
        Binding("backspace", "go_up", "Up"),
        Binding("left", "go_up", "Up"),
        Binding("o", "open_history", "Open History"),
    ]

    def __init__(self, repo_path: str, scroll_to_end: bool = False):
        super().__init__()
        self.logr = get_logger("browser")
        self.repo_path = os.path.abspath(repo_path)
        self.current_path = self.repo_path
        self.selected_device_name: Optional[str] = None
        self.scroll_to_end = scroll_to_end

    def compose(self) -> ComposeResult:
        yield Header()
        self.table = DataTable(id="left")
        self.table.cursor_type = "row"
        self.preview = RichLog(id="right", wrap=True, highlight=False, auto_scroll=self.scroll_to_end)
        yield Horizontal(self.table, self.preview)
        yield Footer()

    def on_mount(self) -> None:
        self._setup_table()
        self._load_directory(self.current_path)
        self.logr.debug("mounted at %s", self.current_path)
        self.table.focus()

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
                if name.lower() == "history":
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

        # Move cursor to first row if available
        if t.row_count:
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
            self.preview.write(f"[b]Path:[/b] {self.current_path}\nEnter to navigate. Press q to quit.")
        else:
            snap = parse_snapshot(key)
            self.preview.clear()
            if snap:
                self.preview.write(snap.content_body)
            else:
                try:
                    with open(key, "r", encoding="utf-8", errors="replace") as f:
                        self.preview.write(f.read())
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
            # Device file selected -> preview already shown; open history via 'o'
            pass

    # Ensure Enter on the DataTable triggers navigation even if the widget handles the key
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:  # type: ignore
        self.action_enter_selected()

    def action_go_up(self) -> None:
        if os.path.abspath(self.current_path) == os.path.abspath(self.repo_path):
            return
        parent = os.path.dirname(self.current_path)
        self._load_directory(parent)

    def action_open_history(self) -> None:
        key = self._selected_row_key()
        self.logr.debug("open_history: %s", key)
        if not key or os.path.isdir(key):
            return
        # Extract device name from filename
        base = os.path.basename(key)
        if not base.lower().endswith(".cfg"):
            return
        self.selected_device_name = os.path.splitext(base)[0]
        self.selected_device_cfg_path = key
        # Exit the app; main will pick up selection
        self.exit()
