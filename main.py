import os
import click
from rich.console import Console

from parser import parse_snapshot
from tui import CommitSelectorApp
from repo_browser import RepoBrowserApp

@click.command()
@click.option(
    '--repo-path',
    required=True,
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    help="Path to the repository of device configurations."
)
@click.option(
    '--device',
    required=False,
    default=None,
    help="Optional device name (without .cfg). If provided, opens its snapshot view."
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
    # If no device specified, launch the repository browser. On selection, return device name.
    if not device:
        browser = RepoBrowserApp(repo_path)
        browser.run()
        if not getattr(browser, 'selected_device_name', None):
            return
        device = browser.selected_device_name

    # Resolve device snapshots directory under history
    device_history_path = os.path.join(repo_path, 'history', device)
    if not os.path.isdir(device_history_path):
        console.print(f"[bold yellow]Note:[/bold yellow] No history folder found for device '{device}'. Proceeding with current config only if present.")

    # Find current device config outside of any 'history' folder
    current_config_path = None
    for root, dirs, files in os.walk(repo_path):
        # prune any 'history' directories from traversal
        dirs[:] = [d for d in dirs if d.lower() != 'history']
        if f"{device}.cfg" in files:
            current_config_path = os.path.join(root, f"{device}.cfg")
            break

    # Collect snapshot files from history
    config_files = []
    if os.path.isdir(device_history_path):
        config_files = sorted([
            os.path.join(device_history_path, f)
            for f in os.listdir(device_history_path) if os.path.isfile(os.path.join(device_history_path, f))
        ])

    if not config_files and not current_config_path:
        console.print(f"[bold yellow]Warning:[/bold yellow] No configuration snapshots or current config found for device '{device}'.")
        return

    snapshots = []
    with console.status("[cyan]Parsing configuration snapshots...[/cyan]"):
        # Include current config if available
        if current_config_path:
            current_snapshot = parse_snapshot(current_config_path)
            if current_snapshot:
                # Make it visually distinct in the table
                current_snapshot = current_snapshot._replace(original_filename=f"Current ({os.path.basename(current_config_path)})")
                snapshots.append(current_snapshot)

        for f in config_files:
            snapshot = parse_snapshot(f)
            if snapshot:
                snapshots.append(snapshot)

    # Sort chronologically
    snapshots.sort(key=lambda s: s.timestamp)

    # Warn if fewer than 2, but still launch the UI to allow preview
    if len(snapshots) < 2:
        console.print("[bold yellow]Note:[/bold yellow] Fewer than two items available; select two to see a diff when more are present.")

    try:
        app = CommitSelectorApp(
            snapshots_data=snapshots,
            scroll_to_end=scroll_to_end,
            layout=layout,
        )
        app.run()

    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred:[/bold red] {e}")

if __name__ == "__main__":
    main()
