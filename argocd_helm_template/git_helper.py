"""Git repository operations and utilities."""

from pathlib import Path
from .utils import log, run_command, CommandError, GIT_NON_INTERACTIVE_ENV


class GitRepo:
    """Represents a Git repository and provides operations on it."""

    def __init__(self, path: Path, verbose: bool = False):
        """
        Initialize GitRepo with a path to a directory within a git repository.

        Args:
            path: Path to a directory (can be repo root or subdirectory)
            verbose: Enable verbose logging for git commands
        """
        self.path = path
        self.verbose = verbose
        self._root: Path | None = None

    def _run_git(self, args: list[str], check: bool = True) -> "subprocess.CompletedProcess":
        """Run a git command in this repository."""
        cmd = ["git", "--no-pager", "-C", str(self.path)] + args
        return run_command(cmd, verbose=self.verbose, check=check, env=GIT_NON_INTERACTIVE_ENV)

    def is_repo(self) -> bool:
        """Check if the path is part of a git repository."""
        try:
            self._run_git(["rev-parse", "--git-dir"])
            return True
        except CommandError:
            return False

    def resolve_root(self) -> Path:
        """
        Resolve the git repository root path.

        Returns:
            Path to the git repository root

        Raises:
            RuntimeError: If path is not in a git repository
        """
        if self._root is not None:
            return self._root

        try:
            result = self._run_git(["rev-parse", "--git-dir"])
        except CommandError:
            raise RuntimeError(
                f"Error: Directory {self.path} is not in a git repository. "
                "Cannot determine git root for ref sources."
            )

        git_dir = result.stdout.strip()
        if git_dir == ".git":
            self._root = self.path
        else:
            # git_dir is a relative or absolute path to .git
            self._root = (self.path / git_dir).resolve().parent if not Path(git_dir).is_absolute() else Path(git_dir).parent

        log(f"Git root: {self._root}")
        return self._root

    def check_file_changes(self, files: list[str]) -> bool:
        """
        Check if any of the given files have uncommitted changes.

        Returns True if any file has changes (both staged and unstaged).
        """
        try:
            result = self._run_git(["diff", "--name-only"] + files, check=False)
        except CommandError:
            return False

        # Also check for staged changes
        try:
            staged_result = self._run_git(["diff", "--cached", "--name-only"] + files, check=False)
        except CommandError:
            staged_result = None

        # Return True if either unstaged or staged changes exist
        return bool(result.stdout.strip() or (staged_result and staged_result.stdout.strip()))

    def extract_file(self, filepath: str, dest: Path, git_ref: str = "HEAD"):
        """
        Extract a file from a git reference and write to destination.

        Raises an exception if the file doesn't exist in git or if git command fails.
        """
        try:
            result = self._run_git(["show", f"{git_ref}:./{filepath}"])
        except CommandError as e:
            raise RuntimeError(f"Failed to extract {filepath} from git: {e.stderr}")

        # Ensure parent directory exists
        dest.parent.mkdir(parents=True, exist_ok=True)

        with open(dest, "w") as f:
            f.write(result.stdout)

    def checkout(self, revision: str):
        """
        Checkout a specific revision (branch/tag) in this repository.

        If the revision is not available locally, fetches from origin and retries.
        """
        log(f"Checking out {revision} in {self.path}...")

        try:
            self._run_git(["checkout", revision])
        except CommandError:
            # Revision not found locally, try fetching and retrying
            log(f"Revision {revision} not found locally, fetching from origin...")

            try:
                self._run_git(["fetch", "origin"])
            except CommandError as e:
                raise RuntimeError(f"Failed to fetch from origin: {e.stderr}")

            # Retry checkout after fetch
            log(f"Retrying checkout of {revision} after fetch...")
            try:
                self._run_git(["checkout", revision])
            except CommandError as e:
                raise RuntimeError(f"Failed to checkout {revision} even after fetch: {e.stderr}")
