from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, RichLog
from textual.containers import Container, Horizontal, Vertical
from textual.binding import Binding
from textual.reactive import reactive
from rich.syntax import Syntax

class DiffViewLog(RichLog):
    BINDINGS = [Binding("space", "page_down", "Page Down", show=False)]

class SelectionDataTable(DataTable):
    BINDINGS = []

class CommitSelectorApp(App):
    # A simplified, correct CSS implementation.
    DEFAULT_CSS = """
    #table-container, #diff_view {
        /* Ensure both panels have a solid background */
        background: $surface;
    }

    #table-container {
        /* Clip the table to prevent render artifacts */
        overflow: hidden;
    }

    #diff_view {
        visibility: hidden;
        /* Add padding so content doesn't touch the border */
        padding: 0 1;
    }

    /* Simple, robust border definition */
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
    ]

    def __init__(self, commits_data, git_engine, scroll_to_end: bool = False, layout: str = 'right'):
        super().__init__()
        self.commits_data = commits_data
        self.git_engine = git_engine
        self.scroll_to_end = scroll_to_end
        self.layout = layout
        self.selected_keys = []
        self.ordered_keys = []

    def compose(self) -> ComposeResult:
        yield Header()
        diff_view = DiffViewLog(id="diff_view", auto_scroll=self.scroll_to_end, wrap=True, highlight=True)
        table = SelectionDataTable(id="commit_table")
        table_container = Container(table, id="table-container")

        if self.layout in ('right', 'left'):
            ordered_widgets = (diff_view, table_container) if self.layout == 'left' else (table_container, diff_view)
            yield Horizontal(*ordered_widgets, classes=f"layout-{self.layout}")
        else:
            ordered_widgets = (diff_view, table_container) if self.layout == 'top' else (table_container, diff_view)
            yield Vertical(*ordered_widgets, classes=f"layout-{self.layout}")
        yield Footer()

    async def on_ready(self) -> None:
        self.setup_table()

    def setup_table(self) -> None:
        table = self.query_one("#commit_table", SelectionDataTable)
        table.cursor_type = "row"
        table.add_column("✓", key="selected_col")
        table.add_column("Hash", key="hash_col")
        table.add_column("Date", key="date_col")
        table.add_column("Author", key="author_col")
        table.add_column("Message", key="message_col")
        for commit in self.commits_data:
            key = commit["hash"]
            self.ordered_keys.append(key)
            table.add_row("", *commit.values(), key=key)
        table.focus()

    def show_diff(self) -> None:
        self.show_hide_diff_key = True
        self.show_focus_next_key = True
        hashes = self.selected_keys
        commit1 = next(c for c in self.commits_data if c['hash'] == hashes[0])
        commit2 = next(c for c in self.commits_data if c['hash'] == hashes[1])
        if commit1['date'] > commit2['date']:
            hashes.reverse()
        diff_text = self.git_engine.get_diff(hashes[0], hashes[1])

        # --- THIS IS THE FIX ---
        # Remove the 'theme="monokai"' argument.
        # This allows the Syntax object to have a transparent background,
        # making the underlying widget background ($surface) visible.
        syntax = Syntax(diff_text, "diff", line_numbers=True, word_wrap=True)

        diff_view = self.query_one("#diff_view", DiffViewLog)
        diff_view.clear()
        diff_view.write(syntax)
        diff_view.styles.visibility = "visible"
        diff_view.focus()

    def hide_diff_panel(self) -> None:
        self.query_one("#diff_view", DiffViewLog).styles.visibility = "hidden"
        self.show_hide_diff_key = False
        self.show_focus_next_key = False
        self.query_one("#commit_table", SelectionDataTable).focus()

    def action_hide_diff(self) -> None:
        self.hide_diff_panel()
        table = self.query_one("#commit_table", SelectionDataTable)
        for key in self.selected_keys:
            table.update_cell(key, "selected_col", "")
        self.selected_keys.clear()

    def action_toggle_row(self) -> None:
        table = self.query_one("#commit_table", SelectionDataTable)
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
            table.update_cell(row_key, "selected_col", "[green]✓[/green]")
        if len(self.selected_keys) == 2:
            self.show_diff()
        else:
            self.hide_diff_panel()