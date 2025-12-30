"""Chart downloading and management utilities."""

import subprocess
import shutil
from pathlib import Path
import yaml
from .argocd_application import ArgocdApplication
from .utils import log, get_helm_repo_name_from_url
from .repo_manager import ensure_helm_repo_added
from .git_helper import clone_or_update_git_repo, checkout_git_revision


def _get_or_create_metadata_file(chart_dir: Path) -> Path:
    """Get path to metadata file tracking chart source information."""
    return chart_dir / ".chart-metadata.yaml"


def _load_chart_metadata(metadata_file: Path) -> dict:
    """Load stored chart metadata. Returns empty dict if file doesn't exist."""
    if not metadata_file.exists():
        return {}

    with open(metadata_file) as f:
        data = yaml.safe_load(f)
        return data or {}


def _save_chart_metadata(metadata_file: Path, metadata: dict):
    """Save chart metadata to file."""
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_file, "w") as f:
        yaml.dump(metadata, f, default_flow_style=False)


def should_download_helm_chart(
    chart_dir: Path,
    chart_name: str,
    version: str,
    repo_url: str,
    is_git: bool = False,
    verbose: bool = False
) -> bool:
    """
    Check if chart needs to be downloaded.

    Compares stored metadata with current configuration. Returns True if:
    - Chart directory doesn't exist
    - Metadata file doesn't exist (first download)
    - repoURL changed
    - chart/path name changed
    - targetRevision changed

    Handles missing/added/changed values gracefully.

    Args:
        chart_dir: Directory where chart is stored
        chart_name: Expected chart name or path
        version: Expected targetRevision (semver or git ref)
        repo_url: Repository URL (HTTP/HTTPS for Helm, git URL, or OCI registry)
        is_git: Whether this is a Git-based chart
        verbose: Enable verbose logging

    Returns:
        True if chart needs to be downloaded, False if already cached with matching config
    """
    if is_git:
        # For Git charts, always return True to ensure we re-copy from latest checkout
        return True

    if not chart_dir.exists():
        return True

    # Check stored metadata
    metadata_file = _get_or_create_metadata_file(chart_dir)
    stored_metadata = _load_chart_metadata(metadata_file)

    # Compare all relevant values
    needs_download = (
        stored_metadata.get("repoURL") != repo_url
        or stored_metadata.get("chartName") != chart_name
        or stored_metadata.get("targetRevision") != version
    )

    if needs_download:
        log(
            f"Chart metadata changed: "
            f"repoURL {stored_metadata.get('repoURL')} -> {repo_url}, "
            f"chartName {stored_metadata.get('chartName')} -> {chart_name}, "
            f"targetRevision {stored_metadata.get('targetRevision')} -> {version}",
            verbose
        )
        return True

    # Additional validation: verify Chart.yaml exists and is readable
    chart_path = chart_dir / chart_name
    chart_yaml = chart_path / "Chart.yaml"

    if not chart_path.exists() or not chart_yaml.exists():
        log(f"Chart directory or Chart.yaml missing at {chart_yaml}, re-downloading", verbose)
        return True

    return False


def _record_chart_metadata(chart_dir: Path, repo_url: str, chart_name: str, version: str):
    """Record metadata about downloaded chart for future comparison."""
    metadata = {
        "repoURL": repo_url,
        "chartName": chart_name,
        "targetRevision": version,
    }
    metadata_file = _get_or_create_metadata_file(chart_dir)
    _save_chart_metadata(metadata_file, metadata)


def _symlink_git_helm_chart(repo_path: Path, chart_path: str, chart_dir: Path, verbose: bool = False):
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


def _download_helm_chart_impl(repo_url: str, chart_name: str, version: str, chart_dir: Path, is_oci: bool = False, verbose: bool = False):
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


def download_helm_chart(app: ArgocdApplication, chart_dir: Path, workdir: Path, verbose: bool = False) -> Path:
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
    chart_source = app.get_helm_chart_source()
    repo_url = chart_source.get("repoURL", "")
    is_git = app.is_helm_git()
    chart_name = chart_source.get("chart" if app.is_helm_repo() else "path", "")
    version = chart_source.get("targetRevision", "").lstrip("v")

    # Calculate the chart path (for both Git and Helm charts)
    actual_chart_dir_name = Path(chart_name).name if is_git else chart_name
    chart_path = chart_dir / actual_chart_dir_name

    if not should_download_helm_chart(chart_dir, chart_name, version, repo_url, is_git, verbose):
        log(f"Chart {chart_name}:{version} already exists in {chart_dir}", verbose)
        return chart_path

    if is_git:
        # Handle Git-based chart
        log(f"Downloading chart {chart_name} from Git revision {version}...", verbose)
        repo_path = clone_or_update_git_repo(repo_url, workdir, verbose)
        checkout_git_revision(repo_path, version, verbose)
        _symlink_git_helm_chart(repo_path, chart_name, chart_dir, verbose)
        # Git charts always re-copy, so no metadata recording needed
    else:
        # Handle Helm registry chart (traditional or OCI)
        is_oci = app.is_helm_oci()

        # Ensure repo is added for non-OCI registries
        if not is_oci:
            repo_name = get_helm_repo_name_from_url(repo_url)
            ensure_helm_repo_added(repo_name, repo_url, verbose)

        # Determine chart reference based on registry type
        if is_oci:
            chart_ref = repo_url
        else:
            chart_ref = get_helm_repo_name_from_url(repo_url)

        log(f"Downloading chart {chart_name}:{version}...", verbose)
        _download_helm_chart_impl(chart_ref, chart_name, version, chart_dir, is_oci, verbose)

        # Record metadata for future cache validation
        _record_chart_metadata(chart_dir, repo_url, chart_name, version)

    return chart_path
