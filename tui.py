from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static
from textual.containers import Container, Horizontal
from textual.binding import Binding
from textual.reactive import reactive
from rich.syntax import Syntax

# This class definition is correct, as you pointed out from the documentation.
class DiffView(Static, can_focus=True):
    """A Static widget that can receive focus."""
    pass

class SelectionDataTable(DataTable):
    BINDINGS = []

class CommitSelectorApp(App):
    DEFAULT_CSS = """
    #commit_table { width: 50%; height: 100%; }
    #diff_view {
        display: none; width: 50%; height: 100%;
        border-left: solid steelblue; padding: 0 1;
        overflow-y: scroll; overflow-x: auto;
    }
    #diff_view:focus {
        border-left: thick yellow;
    }
    """

    show_hide_diff_key = reactive(False, layout=True)
    show_focus_next_key = reactive(False, layout=True)

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "toggle_row", "Toggle Select"),
        Binding("tab", "focus_next", "Switch Panel", show=show_focus_next_key),
        Binding("escape", "hide_diff", "Back to List", show=show_hide_diff_key),
    ]

    def __init__(self, commits_data, git_engine):
        super().__init__()
        self.commits_data = commits_data
        self.git_engine = git_engine
        self.selected_hashes = set()
        self.ordered_keys = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            SelectionDataTable(id="commit_table"),
            # --- THE CRUCIAL FIX IS HERE ---
            # We must use our new DiffView class, not the old Static class.
            DiffView(id="diff_view", expand=True),
        )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(SelectionDataTable)
        # ... (rest of method is unchanged)
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

        # We also query for our new DiffView widget type here
        diff_view = self.query_one(DiffView)
        diff_view.update(syntax)
        diff_view.styles.display = "block"
        diff_view.focus()

    def action_hide_diff(self) -> None:
        table = self.query_one(SelectionDataTable)
        # And here
        diff_view = self.query_one(DiffView)
        diff_view.styles.display = "none"
        
        self.show_hide_diff_key = False
        self.show_focus_next_key = False

        for key in self.selected_hashes:
            table.update_cell(key, "selected_col", "")
        self.selected_hashes.clear()
        table.focus()

    def action_toggle_row(self) -> None:
        table = self.query_one(SelectionDataTable)
        try:
            row_key = self.ordered_keys[table.cursor_row]
        except IndexError:
            return

        if row_key in self.selected_hashes:
            self.selected_hashes.remove(row_key)
            table.update_cell(row_key, "selected_col", "")
        else:
            if len(self.selected_hashes) < 2:
                self.selected_hashes.add(row_key)
                table.update_cell(row_key, "selected_col", "[green]✓[/green]")
            else:
                self.notify("You can only select two commits.", severity="warning")

        if len(self.selected_hashes) == 2:
            self.show_diff()