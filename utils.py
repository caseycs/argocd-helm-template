"""Common utility functions for ArgoCD Helm Template."""

import sys
from pathlib import Path
import yaml


def log(message: str, verbose: bool = False):
    """Print message only if verbose mode is enabled."""
    if verbose:
        print(message, file=sys.stderr)


def get_repo_name_from_url(repo_url: str) -> str:
    """
    Extract repository name from Helm repo URL.
    For https://prometheus-community.github.io/helm-charts, return 'prometheus-community.github.io-helm-charts'
    For https://grafana.github.io/helm-charts, return 'grafana.github.io-helm-charts'
    """
    # Remove http:// or https:// prefix
    if repo_url.startswith("https://"):
        repo_name = repo_url[8:]  # Remove 'https://'
    elif repo_url.startswith("http://"):
        repo_name = repo_url[7:]  # Remove 'http://'
    else:
        repo_name = repo_url

    # Replace slashes with dashes
    repo_name = repo_name.replace("/", "-")

    # Remove trailing dash if present
    repo_name = repo_name.rstrip("-")

    return repo_name


def get_git_cache_dir(repo_url: str, workdir: Path) -> Path:
    """Get the cache directory path for a Git repository in .chart_repo within the working directory."""
    cache_root = workdir / ".chart_repo"
    repo_name = get_repo_name_from_url(repo_url)
    return cache_root / repo_name


def sort_yaml_file(file_path: Path, verbose: bool = False):
    """
    Sort YAML file keys alphabetically.

    Args:
        file_path: Path to YAML file to sort
        verbose: Enable verbose logging
    """
    log(f"Sorting {file_path}...", verbose)

    # Load all YAML documents
    with open(file_path) as f:
        docs = list(yaml.safe_load_all(f))

    # Write back with sorted keys
    with open(file_path, "w") as f:
        for i, doc in enumerate(docs):
            if i > 0:
                f.write("---\n")
            yaml.dump(
                doc,
                f,
                default_flow_style=False,
                sort_keys=True,
                allow_unicode=True,
                width=float("inf")
            )
