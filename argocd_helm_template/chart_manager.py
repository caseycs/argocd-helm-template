"""Chart downloading and management utilities."""

import subprocess
import shutil
from pathlib import Path
import yaml
from .argocd_application import ArgocdApplication
from .utils import log, get_repo_name_from_url
from .repo_manager import ensure_repo_added
from .git_helper import clone_or_update_git_repo, checkout_git_revision


def should_download_chart(chart_dir: Path, chart_name: str, version: str, is_git: bool = False) -> bool:
    """
    Check if chart needs to be downloaded.

    Returns True if:
    - Chart directory doesn't exist
    - Chart.yaml version doesn't match expected version (for Helm charts only)

    For Git charts, always returns True to force re-copy on each run
    (Git checkout will be a no-op if revision is already checked out)
    """
    if is_git:
        # For Git charts, always return True to ensure we re-copy from latest checkout
        return True

    chart_path = chart_dir / chart_name
    chart_yaml = chart_path / "Chart.yaml"

    if not chart_path.exists() or not chart_yaml.exists():
        return True

    # Check version in Chart.yaml
    with open(chart_yaml) as f:
        chart_metadata = yaml.safe_load(f)
        current_version = chart_metadata.get("version", "").lstrip("v")
        return current_version != version


def _symlink_git_chart(repo_path: Path, chart_path: str, chart_dir: Path, verbose: bool = False):
    """Create a symlink from the chart directory to the Git repository chart."""
    # Remove entire .chart directory to ensure clean state
    if chart_dir.exists():
        log(f"Removing existing .chart directory at {chart_dir}", verbose)
        shutil.rmtree(chart_dir)

    # Create fresh .chart directory
    chart_dir.mkdir(parents=True, exist_ok=True)

    # Source path in the Git repo
    source_chart_path = repo_path / chart_path

    if not source_chart_path.exists():
        raise FileNotFoundError(f"Chart not found at {source_chart_path}")

    # Get the chart directory name (last component of the path)
    chart_dir_name = source_chart_path.name

    # Destination symlink path in the .chart directory
    dest_chart_path = chart_dir / chart_dir_name

    log(f"Creating symlink from {dest_chart_path} to {source_chart_path}", verbose)
    dest_chart_path.symlink_to(source_chart_path)


def _download_chart_impl(repo_url: str, chart_name: str, version: str, chart_dir: Path, is_oci: bool = False, verbose: bool = False):
    """Raw download implementation using helm pull."""
    # Remove entire .chart directory to ensure clean state
    if chart_dir.exists():
        log(f"Removing existing .chart directory at {chart_dir}", verbose)
        shutil.rmtree(chart_dir)

    # Create fresh .chart directory
    chart_dir.mkdir(parents=True, exist_ok=True)

    # Build chart reference based on type
    if is_oci:
        chart_ref = f"oci://{repo_url}/{chart_name}"
    else:
        chart_ref = f"{repo_url}/{chart_name}"

    cmd = [
        "helm", "pull",
        chart_ref,
        "--version", version,
        "--untar",
        "--destination", str(chart_dir)
    ]

    log(f"Running: {' '.join(cmd)}", verbose)

    if verbose:
        subprocess.run(cmd, check=True)
    else:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def download_chart(app: ArgocdApplication, chart_dir: Path, workdir: Path, verbose: bool = False) -> Path:
    """
    Download chart and return the path to the chart directory.

    Args:
        app: ArgocdApplication instance (must be validated)
        chart_dir: Directory to download/store charts
        workdir: Working directory
        verbose: Enable verbose logging

    Returns:
        Path to the downloaded/symlinked chart directory
    """
    # Extract chart source info using ArgocdApplication methods
    chart_source = app.get_chart_source()
    repo_url = chart_source.get("repoURL", "")
    is_git = app.is_helm_git()
    chart_name = chart_source.get("chart" if app.is_helm_repo() else "path", "")
    version = chart_source.get("targetRevision", "").lstrip("v")

    # Calculate the chart path (for both Git and Helm charts)
    actual_chart_dir_name = Path(chart_name).name if is_git else chart_name
    chart_path = chart_dir / actual_chart_dir_name

    if not should_download_chart(chart_dir, chart_name, version, is_git):
        log(f"Chart {chart_name}:{version} already exists in {chart_dir}", verbose)
        return chart_path

    if is_git:
        # Handle Git-based chart
        log(f"Downloading chart {chart_name} from Git revision {version}...", verbose)
        repo_path = clone_or_update_git_repo(repo_url, workdir, verbose)
        checkout_git_revision(repo_path, version, verbose)
        _symlink_git_chart(repo_path, chart_name, chart_dir, verbose)
    else:
        # Handle Helm registry chart (traditional or OCI)
        is_oci = app.is_helm_oci()

        # Ensure repo is added for non-OCI registries
        if not is_oci:
            repo_name = get_repo_name_from_url(repo_url)
            ensure_repo_added(repo_name, repo_url, verbose)

        # Determine chart reference based on registry type
        if is_oci:
            chart_ref = repo_url
        else:
            chart_ref = get_repo_name_from_url(repo_url)

        log(f"Downloading chart {chart_name}:{version}...", verbose)
        _download_chart_impl(chart_ref, chart_name, version, chart_dir, is_oci, verbose)

    return chart_path
