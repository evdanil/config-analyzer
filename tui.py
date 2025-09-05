from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, RichLog
from textual.containers import Container, Horizontal, Vertical
from textual.binding import Binding
from textual.reactive import reactive
from parser import Snapshot
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
        # Two orientation containers kept mounted; we toggle visibility and order
        self.h_container = Horizontal(id="h-container")  # type: ignore[attr-defined]
        self.v_container = Vertical(id="v-container")    # type: ignore[attr-defined]
        # Main holder with a layout class
        self.main_panel = Container(self.h_container, self.v_container, id="main-panel")  # type: ignore[attr-defined]
        yield self.main_panel
        yield Footer()

    async def on_ready(self) -> None:
        # Build initial layout, then populate the table
        self._apply_layout()
        self.setup_table()
        self.table.focus()

    def _apply_layout(self) -> None:
        # Ensure widgets are not attached to any container
        try:
            if self.table_container.parent is not None:
                self.table_container.remove()
        except Exception:
            pass
        try:
            if self.diff_view.parent is not None:
                self.diff_view.remove()
        except Exception:
            pass

        # Reset containers' children
        for cont in (self.h_container, self.v_container):
            try:
                for child in list(cont.children):
                    child.remove()
            except Exception:
                pass

        # Apply classes on the main panel for CSS borders
        main = self.main_panel
        # Remove any existing layout-* class
        for c in list(main.classes):
            if str(c).startswith("layout-"):
                main.remove_class(str(c))
        main.add_class(f"layout-{self.layout}")

        # Arrange widgets in the proper container and order
        if self.layout in ("right", "left"):
            # Horizontal
            if self.layout == "left":
                self.h_container.mount(self.diff_view)
                self.h_container.mount(self.table_container)
            else:
                self.h_container.mount(self.table_container)
                self.h_container.mount(self.diff_view)
            # Show horizontal, hide vertical
            self.h_container.styles.display = "block"
            self.v_container.styles.display = "none"
        else:
            # Vertical
            if self.layout == "top":
                self.v_container.mount(self.diff_view)
                self.v_container.mount(self.table_container)
            else:
                self.v_container.mount(self.table_container)
                self.v_container.mount(self.diff_view)
            # Show vertical, hide horizontal
            self.v_container.styles.display = "block"
            self.h_container.styles.display = "none"

    def setup_table(self) -> None:
        table = self.table
        table.cursor_type = "row"
        table.add_column("Sel", key="selected_col", width=3)
        table.add_column("Name", key="name_col")
        table.add_column("Date", key="date_col")
        table.add_column("Author", key="author_col")
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
        table.focus()

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

        diff_view = self.diff_view
        diff_view.clear()
        diff_view.write(renderable)
        diff_view.styles.visibility = "visible"
        diff_view.can_focus = True
        diff_view.focus()

    def hide_diff_panel(self) -> None:
        self.diff_view.styles.visibility = "hidden"
        self.diff_view.can_focus = False
        self.show_hide_diff_key = False
        self.show_focus_next_key = False
        self.table.focus()

    def action_hide_diff(self) -> None:
        self.hide_diff_panel()
        table = self.table
        for key in self.selected_keys:
            table.update_cell(key, "selected_col", "")
        self.selected_keys.clear()

    def action_toggle_row(self) -> None:
        table = self.table
        if not table.has_focus:
            return
        try:
            row_key = self.ordered_keys[table.cursor_row]
        except IndexError:
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
        else:
            self.hide_diff_panel()

    def action_toggle_diff_mode(self) -> None:
        self.diff_mode = "side-by-side" if self.diff_mode == "unified" else "unified"
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
        self.layout = order[(idx + 1) % len(order)]
        self._apply_layout()
        # Keep focus sensible
        if self.show_hide_diff_key:
            self.diff_view.focus()
        else:
            self.table.focus()






