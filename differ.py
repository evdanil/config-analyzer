import subprocess
import tempfile
from typing import TYPE_CHECKING

# Use a forward reference to avoid circular import
if TYPE_CHECKING:
    from parser import Snapshot

def get_diff(snapshot1: "Snapshot", snapshot2: "Snapshot") -> str:
    """
    Generates a colorized, unified diff between the content of two snapshots.
    
    Args:
        snapshot1: The first snapshot object.
        snapshot2: The second snapshot object.

    Returns:
        A string containing the colorized diff output.
    """
    try:
        # Use tempfile.NamedTemporaryFile to handle creation and cleanup
        with tempfile.NamedTemporaryFile(mode='w', delete=True, encoding='utf-8') as file1, tempfile.NamedTemporaryFile(mode='w', delete=True, encoding='utf-8') as file2:
            
            file1.write(snapshot1.content_body)
            file1.flush()  # Ensure content is written to disk
            
            file2.write(snapshot2.content_body)
            file2.flush()

            # Use '-u' for a unified diff, which is standard and readable
            cmd = ["diff", "-u", "--color=always", file1.name, file2.name]
            
            # We don't use check=True because diff returns 1 if files differ.
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Return stdout regardless of the exit code.
            # If there's an actual error, stderr will give a clue.
            return result.stdout if result.stdout else result.stderr

    except FileNotFoundError:
        return "Error: The 'diff' command was not found on your system."
    except Exception as e:
        return f"An unexpected error occurred during diffing: {e}"
    