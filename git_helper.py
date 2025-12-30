"""Git repository operations and utilities."""

import subprocess
from pathlib import Path
from utils import log


def resolve_git_root(workdir: Path, verbose: bool = False) -> Path:
    """
    Resolve the git repository root path from the working directory.

    Checks if workdir is part of a git repository and returns the git root.

    Returns:
        Path to the git repository root

    Raises:
        RuntimeError: If workdir is not in a git repository
    """
    git_check = subprocess.run(
        ["git", "-C", str(workdir), "rev-parse", "--git-dir"],
        capture_output=True,
        text=True
    )

    if git_check.returncode != 0:
        raise RuntimeError(
            f"Error: Working directory {workdir} is not in a git repository. "
            "Cannot determine git root for ref sources."
        )

    git_dir = git_check.stdout.strip()
    if git_dir == ".git":
        log(f"Git root: {workdir}", verbose)
        return workdir
    else:
        # git_dir is a relative or absolute path to .git
        git_root = (workdir / git_dir).resolve().parent if not Path(git_dir).is_absolute() else Path(git_dir).parent
        log(f"Git root: {git_root}", verbose)
        return git_root


def check_git_repo(workdir: Path, verbose: bool = False) -> bool:
    """Check if the working directory is part of a git repository."""
    cmd = ["git", "-C", str(workdir), "rev-parse", "--git-dir"]
    log(f"Running: {' '.join(cmd)}", verbose)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def check_file_changes(workdir: Path, files: list[str], verbose: bool = False) -> bool:
    """
    Check if any of the given files have uncommitted changes.

    Returns True if any file has changes (both staged and unstaged).
    """
    cmd = ["git", "-C", str(workdir), "diff", "--name-only"] + files
    log(f"Running: {' '.join(cmd)}", verbose)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return False

    # Also check for staged changes
    staged_cmd = ["git", "-C", str(workdir), "diff", "--cached", "--name-only"] + files
    log(f"Running: {' '.join(staged_cmd)}", verbose)
    staged_result = subprocess.run(
        staged_cmd,
        capture_output=True,
        text=True
    )

    # Return True if either unstaged or staged changes exist
    return bool(result.stdout.strip() or (staged_result.returncode == 0 and staged_result.stdout.strip()))


def extract_git_file(workdir: Path, filepath: str, dest: Path, git_ref: str = "HEAD", verbose: bool = False):
    """
    Extract a file from a git reference and write to destination.

    Raises an exception if the file doesn't exist in git or if git command fails.
    """
    cmd = ["git", "-C", str(workdir), "show", f"{git_ref}:./{filepath}"]
    log(f"Running: {' '.join(cmd)}", verbose)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to extract {filepath} from git: {result.stderr}")

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
    from utils import get_git_cache_dir

    cache_dir = get_git_cache_dir(repo_url, workdir)

    if not cache_dir.exists():
        # Clone new repo
        log(f"Cloning repository from {repo_url} to {cache_dir}...", verbose)
        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["git", "clone", repo_url, str(cache_dir)]
        log(f"Running: {' '.join(cmd)}", verbose)
        subprocess.run(cmd, check=True, capture_output=True)
    else:
        log(f"Using cached repository at {cache_dir}", verbose)

    return cache_dir


def checkout_git_revision(repo_path: Path, revision: str, verbose: bool = False):
    """
    Checkout a specific revision (branch/tag) in a Git repository.

    If the revision is not available locally, fetches from origin and retries.
    """
    log(f"Checking out {revision} in {repo_path}...", verbose)
    cmd = ["git", "-C", str(repo_path), "checkout", revision]
    log(f"Running: {' '.join(cmd)}", verbose)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        # Revision not found locally, try fetching and retrying
        log(f"Revision {revision} not found locally, fetching from origin...", verbose)
        fetch_cmd = ["git", "-C", str(repo_path), "fetch", "origin"]
        log(f"Running: {' '.join(fetch_cmd)}", verbose)
        fetch_result = subprocess.run(fetch_cmd, capture_output=True, text=True)

        if fetch_result.returncode != 0:
            raise RuntimeError(f"Failed to fetch from origin: {fetch_result.stderr}")

        # Retry checkout after fetch
        log(f"Retrying checkout of {revision} after fetch...", verbose)
        log(f"Running: {' '.join(cmd)}", verbose)
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"Failed to checkout {revision} even after fetch: {result.stderr}")
