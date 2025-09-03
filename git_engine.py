import os
import subprocess
import shutil
import tempfile
from typing import List, Dict

from parser import Snapshot

class GitEngine:
    """A context manager to handle a temporary Git repository for config analysis."""
    
    def __init__(self):
        self.repo_path = tempfile.mkdtemp(prefix="config-analyzer-")

    def __enter__(self):
        """Initializes the git repository when entering the context."""
        try:
            subprocess.run(
                ["git", "init", self.repo_path],
                check=True, capture_output=True, text=True
            )
            # Set a dummy user identity to prevent errors on systems without global git config
            subprocess.run(["git", "-C", self.repo_path, "config", "user.name", "ConfigAnalyzer"], check=True)
            subprocess.run(["git", "-C", self.repo_path, "config", "user.email", "script@localhost"], check=True)
            return self
        except subprocess.CalledProcessError as e:
            error_message = f"Error initializing Git repo.\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
            print(error_message)
            self.cleanup()
            raise Exception(error_message)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleans up the temporary directory when exiting the context."""
        self.cleanup()

    def cleanup(self):
        """Removes the temporary repository directory."""
        if os.path.exists(self.repo_path):
            shutil.rmtree(self.repo_path)

    def commit_snapshot(self, snapshot: Snapshot):
        """Commits a snapshot's content with its specific metadata."""
        target_file = os.path.join(self.repo_path, "device.conf")
        with open(target_file, "w") as f:
            f.write(snapshot.content_body)

        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = snapshot.author
        env["GIT_AUTHOR_EMAIL"] = f"{snapshot.author}@example.com"
        env["GIT_COMMITTER_NAME"] = snapshot.author
        env["GIT_COMMITTER_EMAIL"] = f"{snapshot.author}@example.com"
        
        iso_date = snapshot.timestamp.isoformat()
        commit_message = f"{snapshot.original_filename}"

        try:
            subprocess.run(["git", "-C", self.repo_path, "add", "device.conf"], check=True, capture_output=True)
            
            subprocess.run(
                [
                    "git", "-C", self.repo_path, "commit",
                    "-m", commit_message,
                    f"--date={iso_date}",
                    "--allow-empty"
                ],
                env=env,
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError as e:
            error_message = (
                f"Git command failed.\n"
                f"COMMAND: {' '.join(e.cmd)}\n"
                f"STDOUT: {e.stdout.decode() if e.stdout else ''}\n"
                f"STDERR: {e.stderr.decode() if e.stderr else ''}"
            )
            raise Exception(error_message)

    def get_log(self) -> List[Dict]:
        """Retrieves the commit log in a structured format."""
        log_format = "%h||%ai||%an||%s"
        try:
            result = subprocess.run(
                ["git", "-C", self.repo_path, "log", f"--pretty=format:{log_format}"],
                check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError:
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("||")
            commits.append({
                "hash": parts[0],
                "date": parts[1],
                "author": parts[2],
                "message": parts[3]
            })
        return commits
        
    def get_diff(self, hash1: str, hash2: str) -> str:
        """Gets a colorized diff between two commits."""
        try:
            # FIX #2: Removed 'check=True' because git diff returns 1 if changes are found.
            result = subprocess.run(
                ["git", "-C", self.repo_path, "diff", "--color=always", hash1, hash2],
                capture_output=True, text=True
            )
            return result.stdout
        except Exception as e:
            return f"An error occurred during diff: {e}"
