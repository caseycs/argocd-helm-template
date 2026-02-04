"""Git repository operations and utilities."""

from pathlib import Path
from .utils import log, run_command, CommandError, GIT_NON_INTERACTIVE_ENV


def resolve_git_root(workdir: Path, verbose: bool = False) -> Path:
    """
    Resolve the git repository root path from the working directory.

    Checks if workdir is part of a git repository and returns the git root.

    Returns:
        Path to the git repository root

    Raises:
        RuntimeError: If workdir is not in a git repository
    """
    cmd = ["git", "--no-pager", "-C", str(workdir), "rev-parse", "--git-dir"]
    try:
        result = run_command(cmd, verbose=verbose, env=GIT_NON_INTERACTIVE_ENV)
    except CommandError:
        raise RuntimeError(
            f"Error: Working directory {workdir} is not in a git repository. "
            "Cannot determine git root for ref sources."
        )

    git_dir = result.stdout.strip()
    if git_dir == ".git":
        log(f"Git root: {workdir}")
        return workdir
    else:
        # git_dir is a relative or absolute path to .git
        git_root = (workdir / git_dir).resolve().parent if not Path(git_dir).is_absolute() else Path(git_dir).parent
        log(f"Git root: {git_root}")
        return git_root


def check_git_repo(workdir: Path, verbose: bool = False) -> bool:
    """Check if the working directory is part of a git repository."""
    cmd = ["git", "--no-pager", "-C", str(workdir), "rev-parse", "--git-dir"]
    try:
        run_command(cmd, verbose=verbose, env=GIT_NON_INTERACTIVE_ENV)
        return True
    except CommandError:
        return False


def check_file_changes(workdir: Path, files: list[str], verbose: bool = False) -> bool:
    """
    Check if any of the given files have uncommitted changes.

    Returns True if any file has changes (both staged and unstaged).
    """
    cmd = ["git", "--no-pager", "-C", str(workdir), "diff", "--name-only"] + files
    try:
        result = run_command(cmd, verbose=verbose, env=GIT_NON_INTERACTIVE_ENV)
    except CommandError:
        return False

    # Also check for staged changes
    staged_cmd = ["git", "--no-pager", "-C", str(workdir), "diff", "--cached", "--name-only"] + files
    try:
        staged_result = run_command(staged_cmd, verbose=verbose, env=GIT_NON_INTERACTIVE_ENV)
    except CommandError:
        staged_result = None

    # Return True if either unstaged or staged changes exist
    return bool(result.stdout.strip() or (staged_result and staged_result.stdout.strip()))


def extract_git_file(workdir: Path, filepath: str, dest: Path, git_ref: str = "HEAD", verbose: bool = False):
    """
    Extract a file from a git reference and write to destination.

    Raises an exception if the file doesn't exist in git or if git command fails.
    """
    cmd = ["git", "--no-pager", "-C", str(workdir), "show", f"{git_ref}:./{filepath}"]
    try:
        result = run_command(cmd, verbose=verbose, env=GIT_NON_INTERACTIVE_ENV)
    except CommandError as e:
        raise RuntimeError(f"Failed to extract {filepath} from git: {e.stderr}")

    # Ensure parent directory exists
    dest.parent.mkdir(parents=True, exist_ok=True)

    with open(dest, "w") as f:
        f.write(result.stdout)


def clone_or_update_git_repo(repo_url: str, workdir: Path, verbose: bool = False) -> Path:
    """
    Clone a Git repository in the cache directory if it doesn't exist.

    Returns:
        Path to the cached repository
    """
    from .utils import get_git_cache_dir

    cache_dir = get_git_cache_dir(repo_url, workdir)

    if not cache_dir.exists():
        # Clone new repo
        log(f"Cloning repository from {repo_url} to {cache_dir}...")
        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["git", "--no-pager", "clone", repo_url, str(cache_dir)]
        run_command(cmd, verbose=verbose, env=GIT_NON_INTERACTIVE_ENV)
    else:
        log(f"Using cached repository at {cache_dir}")

    return cache_dir


def checkout_git_revision(repo_path: Path, revision: str, verbose: bool = False):
    """
    Checkout a specific revision (branch/tag) in a Git repository.

    If the revision is not available locally, fetches from origin and retries.
    """
    log(f"Checking out {revision} in {repo_path}...")
    cmd = ["git", "--no-pager", "-C", str(repo_path), "checkout", revision]

    try:
        run_command(cmd, verbose=verbose, env=GIT_NON_INTERACTIVE_ENV)
    except CommandError:
        # Revision not found locally, try fetching and retrying
        log(f"Revision {revision} not found locally, fetching from origin...")
        fetch_cmd = ["git", "--no-pager", "-C", str(repo_path), "fetch", "origin"]

        try:
            run_command(fetch_cmd, verbose=verbose, env=GIT_NON_INTERACTIVE_ENV)
        except CommandError as e:
            raise RuntimeError(f"Failed to fetch from origin: {e.stderr}")

        # Retry checkout after fetch
        log(f"Retrying checkout of {revision} after fetch...")
        try:
            run_command(cmd, verbose=verbose, env=GIT_NON_INTERACTIVE_ENV)
        except CommandError as e:
            raise RuntimeError(f"Failed to checkout {revision} even after fetch: {e.stderr}")
