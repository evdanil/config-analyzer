import re
from datetime import datetime
from typing import Optional, NamedTuple
from dateutil.parser import parse

# Using a NamedTuple for a lightweight, immutable data structure.
class Snapshot(NamedTuple):
    """Represents a single parsed configuration snapshot."""
    path: str
    author: str
    timestamp: datetime
    content_body: str
    original_filename: str

# Pre-compile the regex for efficiency.
CHANGE_RE = re.compile(r"^\! Last configuration change at (.*?) by (\S+)$", re.MULTILINE)

def parse_snapshot(file_path: str) -> Optional[Snapshot]:
    """
    Parses a configuration snapshot file to extract metadata and content.

    Args:
        file_path: The path to the configuration snapshot file.

    Returns:
        A Snapshot object if parsing is successful, otherwise None.
    """
    try:
        with open(file_path, 'r') as f:
            full_content = f.read()
    except IOError:
        return None

    match = CHANGE_RE.search(full_content)
    if not match:
        return None

    date_str, author = match.groups()

    try:
        # dateutil.parser is excellent at handling various date formats.
        timestamp = parse(date_str.replace("GMT", "+0000"))
    except (ValueError, TypeError):
        return None
        
    # Simple logic to split frontmatter from the body. Assumes the first
    # line not starting with '!' or 'Building' or 'Current' marks the real config.
    lines = full_content.splitlines()
    body_start_index = 0
    for i, line in enumerate(lines):
        if line and not line.startswith(('!', 'Building', 'Current')):
            body_start_index = i
            break
            
    content_body = "\n".join(lines[body_start_index:])
    original_filename = file_path.split('/')[-1]

    return Snapshot(
        path=file_path,
        author=author,
        timestamp=timestamp,
        content_body=content_body,
        original_filename=original_filename
    )
