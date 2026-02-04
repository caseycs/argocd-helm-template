"""Helm repository management functions."""

import yaml
from .utils import log, run_command, CommandError


def is_repo_added(repo_name: str, verbose: bool = False) -> bool:
    """Check if Helm repository is already added."""
    cmd = ["helm", "repo", "list", "-o", "json"]
    try:
        result = run_command(cmd, verbose=verbose, check=False)
    except CommandError:
        # If helm repo list fails, assume no repos are added
        return False

    if result.returncode != 0:
        return False

    try:
        repos = yaml.safe_load(result.stdout) or []
        return any(repo.get("name") == repo_name for repo in repos)
    except:
        return False


def ensure_helm_repo_added(repo_name: str, repo_url: str, verbose: bool = False):
    """Ensure Helm repository is added and updated."""
    if not is_repo_added(repo_name, verbose):
        log(f"Adding Helm repository {repo_name}...", verbose)
        cmd = ["helm", "repo", "add", repo_name, repo_url]
        run_command(cmd, verbose=verbose)
    else:
        log(f"Helm repository {repo_name} already added", verbose)

    # Update repo to get latest chart info
    log(f"Updating Helm repository {repo_name}...", verbose)
    cmd = ["helm", "repo", "update", repo_name]
    run_command(cmd, verbose=verbose)
