from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, RichLog
from textual.containers import Container, Horizontal, Vertical # Import Vertical
from textual.binding import Binding
from textual.reactive import reactive
from rich.syntax import Syntax

class DiffViewLog(RichLog):
    BINDINGS = [Binding("space", "page_down", "Page Down", show=False)]

class SelectionDataTable(DataTable):
    BINDINGS = []

class CommitSelectorApp(App):
    # --- CHANGE #1: The CSS is now refactored to handle all layout classes ---
    DEFAULT_CSS = """
    /* Common styles for both widgets */
    #diff_view {
        display: none;
    }

    /* Horizontal Layouts (right, left) */
    .layout-right #commit_table, .layout-left #commit_table,
    .layout-right #diff_view, .layout-left #diff_view {
        width: 50%;
        height: 100%;
    }
    .layout-right #diff_view { border-left: solid steelblue; }
    .layout-right #diff_view:focus { border-left: thick yellow; }
    .layout-left #diff_view { border-right: solid steelblue; }
    .layout-left #diff_view:focus { border-right: thick yellow; }

    /* Vertical Layouts (bottom, top) */
    .layout-bottom #commit_table, .layout-top #commit_table,
    .layout-bottom #diff_view, .layout-top #diff_view {
        height: 50%;
        width: 100%;
    }
    .layout-bottom #diff_view { border-top: solid steelblue; }
    .layout-bottom #diff_view:focus { border-top: thick yellow; }
    .layout-top #diff_view { border-bottom: solid steelblue; }
    .layout-top #diff_view:focus { border-bottom: thick yellow; }
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
        self.layout = layout # Store the layout preference
        self.selected_keys = []
        self.ordered_keys = []

    # --- CHANGE #2: The compose method now builds the layout dynamically ---
    def compose(self) -> ComposeResult:
        yield Header()

        # Define the widgets once
        table = SelectionDataTable(id="commit_table")
        diff_view = DiffViewLog(id="diff_view", auto_scroll=self.scroll_to_end, wrap=True, highlight=True)

        # Choose the container and order based on the layout
        if self.layout in ('right', 'left'):
            container = Horizontal(classes=f"layout-{self.layout}")
            first_widget = diff_view if self.layout == 'left' else table
            second_widget = table if self.layout == 'left' else diff_view
        else: # top or bottom
            container = Vertical(classes=f"layout-{self.layout}")
            first_widget = diff_view if self.layout == 'top' else table
            second_widget = table if self.layout == 'top' else diff_view
        
        with container:
            yield first_widget
            yield second_widget
            
        yield Footer()

    # No further changes are needed in the rest of the file.
    # The logic is independent of the layout.
    def on_mount(self) -> None:
        table = self.query_one(SelectionDataTable)
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

    def show_diff(self) -> None:
        self.show_hide_diff_key = True
        self.show_focus_next_key = True
        hashes = self.selected_keys
        commit1 = next(c for c in self.commits_data if c['hash'] == hashes[0])
        commit2 = next(c for c in self.commits_data if c['hash'] == hashes[1])
        if commit1['date'] > commit2['date']:
            hashes.reverse()
        diff_text = self.git_engine.get_diff(hashes[0], hashes[1])
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True, word_wrap=True)
        diff_view = self.query_one(DiffViewLog)
        diff_view.clear()
        diff_view.write(syntax)

        diff_view.styles.display = "block"
        diff_view.focus()

    def hide_diff_panel(self) -> None:
        self.query_one(DiffViewLog).styles.display = "none"
        self.show_hide_diff_key = False
        self.show_focus_next_key = False
        self.query_one(SelectionDataTable).focus()

    def action_hide_diff(self) -> None:
        self.hide_diff_panel()
        table = self.query_one(SelectionDataTable)
        for key in self.selected_keys:
            table.update_cell(key, "selected_col", "")
        self.selected_keys.clear()

    def action_toggle_row(self) -> None:
        table = self.query_one(SelectionDataTable)
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