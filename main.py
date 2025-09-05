import os
import click
from rich.console import Console

from parser import parse_snapshot
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
@click.option(
    '--scroll-to-end',
    is_flag=True,
    default=False,
    help="Automatically scroll to the end of the diff view on load.",
    show_default=True,
)
# --- CHANGE: Add a new command-line option for the layout ---
@click.option(
    '--layout',
    type=click.Choice(['right', 'left', 'bottom', 'top'], case_sensitive=False),
    default='right',
    help="Position of the diff panel relative to the commit list.",
    show_default=True,
)
def main(repo_path, device, scroll_to_end, layout):
    """
    An interactive tool to analyze network device configuration changes.
    """
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

    if len(snapshots) < 2:
        console.print("[bold yellow]Need at least two valid snapshots to compare.[/bold yellow]")
        return

    try:
        app = CommitSelectorApp(
            snapshots_data=snapshots, # Pass snapshots directly
            scroll_to_end=scroll_to_end, 
            layout=layout
        )
        app.run()

    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred:[/bold red] {e}")

if __name__ == "__main__":
    main()