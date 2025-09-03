from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, RichLog
from textual.containers import Container, Horizontal
from textual.binding import Binding
from textual.reactive import reactive
from rich.syntax import Syntax

class DiffViewLog(RichLog):
    BINDINGS = [Binding("space", "page_down", "Page Down", show=False)]

class SelectionDataTable(DataTable):
    BINDINGS = []

class CommitSelectorApp(App):
    DEFAULT_CSS = """
    #commit_table { width: 50%; height: 100%; }
    #diff_view {
        display: none; width: 50%; height: 100%;
        border-left: solid steelblue;
    }
    #diff_view:focus { border-left: thick yellow; }
    """

    show_hide_diff_key = reactive(False, layout=True)
    show_focus_next_key = reactive(False, layout=True)

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "toggle_row", "Toggle Select"),
        Binding("tab", "focus_next", "Switch Panel", show=show_focus_next_key),
        Binding("escape", "hide_diff", "Back to List", show=show_hide_diff_key),
    ]

    def __init__(self, commits_data, git_engine, scroll_to_end: bool = False):
        super().__init__()
        self.commits_data = commits_data
        self.git_engine = git_engine
        self.scroll_to_end = scroll_to_end
        self.selected_hashes = set()
        self.ordered_keys = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            SelectionDataTable(id="commit_table"),
            DiffViewLog(id="diff_view", auto_scroll=self.scroll_to_end, wrap=True, highlight=True),
        )
        yield Footer()

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
        hashes = list(self.selected_hashes)
        commit1 = next(c for c in self.commits_data if c['hash'] == hashes[0])
        commit2 = next(c for c in self.commits_data if c['hash'] == hashes[1])
        if commit1['date'] > commit2['date']:
            hashes.reverse()
        diff_text = self.git_engine.get_diff(hashes[0], hashes[1])
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True, word_wrap=True)
        diff_view = self.query_one(DiffViewLog)
        diff_view.clear()
        # --- CHANGE #2: Use the configurable scroll option ---
        diff_view.write(syntax)
        diff_view.styles.display = "block"
        diff_view.focus()
    
    # --- CHANGE #3: New, simpler method to ONLY hide the panel ---
    def hide_diff_panel(self) -> None:
        """Hides the diff panel and resets its bindings, without changing selections."""
        self.query_one(DiffViewLog).styles.display = "none"
        self.show_hide_diff_key = False
        self.show_focus_next_key = False
        self.query_one(SelectionDataTable).focus()

    # --- CHANGE #4: The 'escape' action is now a full reset ---
    def action_hide_diff(self) -> None:
        """Called on Escape. Hides panel and clears ALL selections."""
        self.hide_diff_panel() # First, hide the UI
        table = self.query_one(SelectionDataTable)
        for key in self.selected_hashes: # Then, clear the data
            table.update_cell(key, "selected_col", "")
        self.selected_hashes.clear()

    # --- CHANGE #5: The toggle logic is completely rewritten and robust ---
    def action_toggle_row(self) -> None:
        """Called when the user presses the spacebar."""
        table = self.query_one(SelectionDataTable)
        if not table.has_focus:
            return

        try:
            row_key = self.ordered_keys[table.cursor_row]
        except IndexError:
            return

        if row_key in self.selected_hashes:
            # If it's already selected, just remove it.
            self.selected_hashes.remove(row_key)
            table.update_cell(row_key, "selected_col", "")
        else:
            # If it's not selected, add it (if there's space).
            if len(self.selected_hashes) < 2:
                self.selected_hashes.add(row_key)
                table.update_cell(row_key, "selected_col", "[green]✓[/green]")
            else:
                self.notify("You can only select two commits.", severity="warning")

        # Finally, update the UI to reflect the new state.
        if len(self.selected_hashes) == 2:
            self.show_diff()
        else:
            self.hide_diff_panel()