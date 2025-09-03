import os
import click
from rich.console import Console

from parser import parse_snapshot
from git_engine import GitEngine
from tui import CommitSelectorApp

@click.command()
@click.option(
    '--repo-path',
    required=True,
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    help="Path to the repository of device configurations."
)
@click.option(
    '--device',
    required=True,
    help="Name of the device folder inside the history folder."
)
# --- CHANGE: Add a new command-line flag for scrolling behavior ---
@click.option(
    '--scroll-to-end',
    is_flag=True,
    default=False,
    help="Automatically scroll to the end of the diff view on load."
)
def main(repo_path, device, scroll_to_end):
    """
    An interactive tool to analyze network device configuration changes.
    """
    # ... (rest of the file is unchanged until the app is created) ...
    console = Console()
    device_path = os.path.join(repo_path, 'history', device)

    if not os.path.isdir(device_path):
        console.print(f"[bold red]Error:[/bold red] Device folder '{device}' not found at '{device_path}'")
        return

    config_files = sorted([
        os.path.join(device_path, f)
        for f in os.listdir(device_path) if os.path.isfile(os.path.join(device_path, f))
    ])

    if not config_files:
        console.print(f"[bold yellow]Warning:[/bold yellow] No configuration files found for device '{device}'.")
        return

    snapshots = []
    with console.status("[cyan]Parsing configuration snapshots...[/cyan]"):
        for f in config_files:
            snapshot = parse_snapshot(f)
            if snapshot:
                snapshots.append(snapshot)
    
    snapshots.sort(key=lambda s: s.timestamp)

    try:
        with GitEngine() as git:
            with console.status("[cyan]Building temporary git history...[/cyan]"):
                for snapshot in snapshots:
                    git.commit_snapshot(snapshot)
            
            commits = git.get_log()
            if len(commits) < 2:
                console.print("[bold yellow]Need at least two valid snapshots to compare.[/bold yellow]")
                return

            # --- CHANGE: Pass the new option into the app ---
            app = CommitSelectorApp(commits, git, scroll_to_end=scroll_to_end)
            app.run()

    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred:[/bold red] {e}")

if __name__ == "__main__":
    main()