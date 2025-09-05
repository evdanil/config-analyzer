import os
import click
from rich.console import Console

from parser import parse_snapshot
from debug import get_logger
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
@click.option(
    '--layout',
    type=click.Choice(['right', 'left', 'bottom', 'top'], case_sensitive=False),
    default='right',
    help="Position of the diff panel relative to the commit list.",
    show_default=True,
)
@click.option(
    '--history-dir',
    default='history',
    show_default=True,
    help="Folder name that contains device history (e.g. 'history').",
)
@click.option(
    '--debug',
    is_flag=True,
    default=False,
    help='Enable verbose debug logging to tui_debug.log',
    show_default=True,
)
def main(repo_path, device, scroll_to_end, layout, history_dir, debug):
    """
    An interactive tool to analyze network device configuration changes.
    """
    console = Console()
    log = get_logger("main")
    if debug:
        os.environ['CONFIG_ANALYZER_DEBUG'] = '1'
        console.print('[dim]Debug logging enabled -> tui_debug.log[/dim]')
    log.debug(
        "start: repo=%s device=%s layout=%s history_dir=%s scroll_to_end=%s",
        repo_path,
        device,
        layout,
        history_dir,
        scroll_to_end,
    )
    # Helper: resolve device snapshots directory under history (prefer nearest to selected cfg path)
    def _find_device_history(repo_root, dev, cfg_path):
        # Prefer nearest 'history/<dev>' relative to the selected cfg directory, walking up to repo root
        if cfg_path:
            repo_abs = os.path.abspath(repo_root)
            cur = os.path.dirname(os.path.abspath(cfg_path))
            while True:
                cand = os.path.join(cur, history_dir, dev)
                if os.path.isdir(cand):
                    return cand
                if os.path.abspath(cur) == repo_abs:
                    break
                parent = os.path.dirname(cur)
                if parent == cur:
                    break
                cur = parent
        # Fallback 1: repo root history
        cand = os.path.join(repo_root, history_dir, dev)
        if os.path.isdir(cand):
            return cand
        # Fallback 2: scan repo for any 'history/<dev>' path; pick shortest path
        hits = []
        for root, dirs, _files in os.walk(repo_root):
            if any(d.lower() == history_dir_l for d in dirs):
                path = os.path.join(root, history_dir, dev)
                if os.path.isdir(path):
                    hits.append(path)
        if hits:
            hits.sort(key=lambda p: len(p))
            return hits[0]
        return None

    # Persist layout preference across views
    layout_pref = layout

    # Loop to allow returning to the device browser from snapshot view
    selected_cfg_path = None
    while True:
        # If no device specified or user requested back, launch the browser
        if not device:
            try:
                console.clear()
            except Exception:
                pass
            browser = RepoBrowserApp(
                repo_path,
                scroll_to_end=scroll_to_end,
                start_path=selected_cfg_path,
                start_layout=layout_pref,
                history_dir=history_dir,
            )
            browser.run()
            if not getattr(browser, 'selected_device_name', None):
                return
            device = browser.selected_device_name
            selected_cfg_path = getattr(browser, 'selected_device_cfg_path', None)
            layout_pref = getattr(browser, 'layout', layout_pref)
            log.debug(
                "browser: selected device=%s cfg=%s layout=%s",
                device,
                selected_cfg_path,
                layout_pref,
            )

        device_history_path = _find_device_history(repo_path, device, selected_cfg_path)
        if not device_history_path:
            console.print(f"[bold yellow]Note:[/bold yellow] No history folder found for device '{device}'. Proceeding with current config only if present.")
        else:
            log.debug("history_dir=%s", device_history_path)

        # Find current device config outside of any 'history' folder
        current_config_path = None
        if selected_cfg_path:
            current_config_path = selected_cfg_path
        else:
        for root, dirs, files in os.walk(repo_path):
            # prune any 'history' directories from traversal
            dirs[:] = [d for d in dirs if d.lower() != history_dir_l]
                if f"{device}.cfg" in files:
                    current_config_path = os.path.join(root, f"{device}.cfg")
                    break

        # Collect snapshot files from history
        config_files = []
        if device_history_path and os.path.isdir(device_history_path):
            config_files = sorted([
                os.path.join(device_history_path, f)
                for f in os.listdir(device_history_path)
                if os.path.isfile(os.path.join(device_history_path, f)) and f.lower().endswith('.cfg')
            ])
        log.debug("snapshots found=%d current_cfg=%s", len(config_files), bool(selected_cfg_path))

        if not config_files and not current_config_path:
            console.print(f"[bold yellow]Warning:[/bold yellow] No configuration snapshots or current config found for device '{device}'.")
            return

        snapshots = []
        with console.status("[cyan]Parsing configuration snapshots...[/cyan]"):
            # Include current config if available
            if current_config_path:
                current_snapshot = parse_snapshot(current_config_path)
                if current_snapshot:
                    current_snapshot = current_snapshot._replace(original_filename="Current")
                    snapshots.append(current_snapshot)

            for f in config_files:
                snapshot = parse_snapshot(f)
                if snapshot:
                    snapshots.append(snapshot)

        # Order: Current first (if present), then snapshots by timestamp DESC (most recent on top)
        current_item = None
        others = []
        for s in snapshots:
            if s.original_filename == "Current" and current_item is None:
                current_item = s
            else:
                others.append(s)
        others.sort(key=lambda s: s.timestamp, reverse=True)
        snapshots = ([current_item] if current_item else []) + others

        # Warn if fewer than 2, but still launch the UI to allow preview
        if len(snapshots) < 2:
            console.print("[bold yellow]Note:[/bold yellow] Fewer than two items available; select two to see a diff when more are present.")

        try:
            try:
                console.clear()
            except Exception:
                pass
            app = CommitSelectorApp(
                snapshots_data=snapshots,
                scroll_to_end=scroll_to_end,
                layout=layout_pref,
            )
            app.run()

        except Exception as e:
            console.print(f"[bold red]An unexpected error occurred:[/bold red] {e}")
            return

        # Save layout preference, then handle navigation
        layout_pref = getattr(app, 'layout', layout_pref)
        log.debug("snapshot_view_done: layout=%s navigate_back=%s", layout_pref, getattr(app, 'navigate_back', False))
        # If user requested to go back, reset device to reopen the browser
        if getattr(app, 'navigate_back', False):
            # Reopen browser at the directory of current config if available
            device = None
            selected_cfg_path = current_config_path
            continue
        break

if __name__ == "__main__":
    main()





