"""Helm repository management functions."""

import subprocess
import yaml
from .utils import log, get_repo_name_from_url


def is_repo_added(repo_name: str, verbose: bool = False) -> bool:
    """Check if Helm repository is already added."""
    result = subprocess.run(
        ["helm", "repo", "list", "-o", "json"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        # If helm repo list fails, assume no repos are added
        return False

    try:
        repos = yaml.safe_load(result.stdout) or []
        return any(repo.get("name") == repo_name for repo in repos)
    except:
        return False


def ensure_repo_added(repo_name: str, repo_url: str, verbose: bool = False):
    """Ensure Helm repository is added and updated."""
    if not is_repo_added(repo_name, verbose):
        log(f"Adding Helm repository {repo_name}...", verbose)
        cmd = ["helm", "repo", "add", repo_name, repo_url]
        log(f"Running: {' '.join(cmd)}", verbose)

        if verbose:
            subprocess.run(cmd, check=True)
        else:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        log(f"Helm repository {repo_name} already added", verbose)

    # Update repo to get latest chart info
    log(f"Updating Helm repository {repo_name}...", verbose)
    cmd = ["helm", "repo", "update", repo_name]
    log(f"Running: {' '.join(cmd)}", verbose)

    if verbose:
        subprocess.run(cmd, check=True)
    else:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
