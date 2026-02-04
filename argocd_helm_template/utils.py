"""Common utility functions for ArgoCD Helm Template."""

import os
import subprocess
import sys
from pathlib import Path
import yaml


def log(message: str, verbose: bool = False):
    """Print message only if verbose mode is enabled."""
    if verbose:
        print(message, file=sys.stderr)


class CommandError(Exception):
    """Exception raised when an external command fails."""
    def __init__(self, cmd: list[str], returncode: int, stdout: str, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(f"Command failed with exit code {returncode}: {' '.join(cmd)}")


def run_command(
    cmd: list[str],
    verbose: bool = False,
    check: bool = True,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """
    Run an external command with consistent behavior.

    - Always logs command in verbose mode
    - Always captures output (never uses DEVNULL)
    - Shows output in verbose mode (both success and failure)
    - Fails on non-zero exit code unless check=False

    Args:
        cmd: Command and arguments as list
        verbose: Log command before execution and show output
        check: Raise CommandError on non-zero exit code
        cwd: Working directory for command
        env: Additional environment variables (merged with current env)

    Returns:
        CompletedProcess with stdout and stderr

    Raises:
        CommandError: If check=True and command returns non-zero exit code
    """
    log(f"Running: {' '.join(cmd)}", verbose)

    # Merge environment variables
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=run_env,
    )

    # Show output in verbose mode
    if verbose:
        if result.stdout:
            log(f"stdout:\n{result.stdout}", verbose)
        if result.stderr:
            log(f"stderr:\n{result.stderr}", verbose)

    if check and result.returncode != 0:
        raise CommandError(cmd, result.returncode, result.stdout, result.stderr)

    return result


# Git environment to disable interactive prompts
GIT_NON_INTERACTIVE_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
}


def get_helm_repo_name_from_url(repo_url: str) -> str:
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
    repo_name = get_helm_repo_name_from_url(repo_url)
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
