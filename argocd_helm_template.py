#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pyyaml",
# ]
# ///

"""
Extract chart info from application.yaml, download chart, and run helm template.
Usage: uv run argocd_helm_template.py [--workdir DIR] [--verbose] [--secrets] [additional helm template args]
"""

import argparse
import base64
import subprocess
import sys
from pathlib import Path
import yaml
import shutil


def log(message: str, verbose: bool = False):
    """Print message only if verbose mode is enabled."""
    if verbose:
        print(message, file=sys.stderr)


def load_application_yaml(path: Path = Path("application.yaml")) -> dict:
    """Load and parse the application.yaml file."""
    with open(path) as f:
        return yaml.safe_load(f)


def extract_chart_info(app_yaml: dict) -> tuple[str, str, str, bool]:
    """
    Extract chart repository, name, version, and chart type from application.yaml.

    Returns:
        tuple: (repo_url, chart_name, version, is_git_chart)
    """
    sources = app_yaml.get("spec", {}).get("sources", [])

    # Find the source with chart info (helm chart or git-based chart)
    for source in sources:
        if "chart" in source:
            # Traditional Helm chart repository
            repo_url = source.get("repoURL", "")
            chart_name = source.get("chart", "")
            version = source.get("targetRevision", "").lstrip("v")
            return repo_url, chart_name, version, False
        elif "path" in source:
            # Git-based chart
            repo_url = source.get("repoURL", "")
            chart_path = source.get("path", "")
            version = source.get("targetRevision", "")
            return repo_url, chart_path, version, True

    raise ValueError("Could not find chart information in application.yaml")


def is_oci_registry(repo_url: str) -> bool:
    """Check if the repository URL is an OCI registry."""
    return not repo_url.startswith(("http://", "https://"))


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


def get_git_cache_dir(repo_url: str) -> Path:
    """Get the cache directory path for a Git repository."""
    cache_root = Path.home() / ".argocd_template"
    repo_name = get_repo_name_from_url(repo_url)
    return cache_root / repo_name


def clone_or_update_git_repo(repo_url: str, verbose: bool = False) -> Path:
    """
    Clone a Git repository in the cache directory if it doesn't exist.

    Returns:
        Path to the cached repository
    """
    cache_dir = get_git_cache_dir(repo_url)

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


def _copy_git_chart(repo_path: Path, chart_path: str, chart_dir: Path, verbose: bool = False):
    """Copy a chart from a Git repository to the chart directory."""
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

    # Destination in the .chart directory
    dest_chart_path = chart_dir / chart_dir_name

    log(f"Copying chart from {source_chart_path} to {dest_chart_path}", verbose)
    shutil.copytree(source_chart_path, dest_chart_path)


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


def download_chart(repo_url: str, chart_name: str, version: str, chart_dir: Path, is_git: bool = False, verbose: bool = False):
    """Wrapper that checks if download is needed and downloads chart."""
    if not should_download_chart(chart_dir, chart_name, version, is_git):
        log(f"Chart {chart_name}:{version} already exists in {chart_dir}", verbose)
        return

    if is_git:
        # Handle Git-based chart
        log(f"Downloading chart {chart_name} from Git revision {version}...", verbose)
        repo_path = clone_or_update_git_repo(repo_url, verbose)
        checkout_git_revision(repo_path, version, verbose)
        _copy_git_chart(repo_path, chart_name, chart_dir, verbose)
    else:
        # Handle Helm registry chart (traditional or OCI)
        is_oci = is_oci_registry(repo_url)

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


class LiteralString(str):
    """String subclass to mark strings that should use literal block scalar style."""
    pass


def represent_literal_str(dumper, data):
    """Custom YAML representer for LiteralString to use literal block scalar style."""
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')


def represent_str(dumper, data):
    """Custom YAML representer for regular strings to preserve multiline formatting."""
    if '\n' in data:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


def process_secrets(yaml_output: str, secrets: bool = False, verbose: bool = False) -> str:
    """
    Post-process helm template output to decode base64 values in Secrets.

    Args:
        yaml_output: Raw YAML output from helm template
        secrets: Whether to decode base64 values in Secrets
        verbose: Enable verbose logging

    Returns:
        Processed YAML output with decoded Secret values (if secrets=True)
    """
    # If not decoding secrets, return original output
    if not secrets:
        return yaml_output

    # Load all YAML documents using native yaml.safe_load_all
    documents = []
    try:
        for doc in yaml.safe_load_all(yaml_output):
            if doc is None:
                continue

            # Process Secrets
            if isinstance(doc, dict) and doc.get('kind') == 'Secret':
                log(f"Processing Secret: {doc.get('metadata', {}).get('name', 'unknown')}", verbose)

                # Decode data section
                if 'data' in doc and isinstance(doc['data'], dict):
                    for key, value in doc['data'].items():
                        if isinstance(value, str):
                            try:
                                decoded = base64.b64decode(value).decode('utf-8')
                                # Wrap in LiteralString to force literal block scalar style
                                doc['data'][key] = LiteralString(decoded)
                                log(f"  Decoded key: {key}", verbose)
                            except Exception as e:
                                log(f"  Failed to decode key {key}: {e}", verbose)
                                # Keep original value if decoding fails
                                pass

            documents.append(doc)
    except yaml.YAMLError as e:
        log(f"Warning: Failed to parse YAML: {e}", verbose)
        return yaml_output  # Return original if parsing fails

    # Create custom dumper with our representers
    class CustomDumper(yaml.SafeDumper):
        pass

    CustomDumper.add_representer(LiteralString, represent_literal_str)
    CustomDumper.add_representer(str, represent_str)

    # Convert documents back to YAML
    result_parts = []
    for doc in documents:
        result_parts.append(yaml.dump(
            doc,
            Dumper=CustomDumper,
            default_flow_style=False,
            sort_keys=False,
            width=float("inf"),
            allow_unicode=True
        ))

    return '---\n' + '\n---\n'.join(result_parts)


def run_helm_template(chart_path: Path, version: str, extra_args: list[str], values_file: Path = Path("values.yaml"), output_dir: Path = Path("."), secrets: bool = False, verbose: bool = False):
    """Run helm template command and optionally post-process Secrets to decode base64 values."""
    cmd = [
        "helm", "template",
        str(chart_path),
        "--version", f"v{version}",
        "-f", str(values_file)
    ] + extra_args

    log(f"Running: {' '.join(cmd)}", verbose)

    # Run helm template and capture output
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    stdout_output, stderr_output = process.communicate()

    if process.returncode != 0:
        print(stderr_output, file=sys.stderr)
        sys.exit(process.returncode)
    elif verbose and stderr_output:
        print(stderr_output, file=sys.stderr)

    # Post-process to decode Secret values if requested
    if secrets:
        log("Post-processing Secrets to decode base64 values...", verbose)
    processed_output = process_secrets(stdout_output, secrets, verbose)

    # Determine output filename based on secrets flag
    manifest_filename = ".manifest.secrets.yaml" if secrets else ".manifest.yaml"
    manifest_path = output_dir / manifest_filename

    # Write processed output to both stdout and manifest file
    print(processed_output, end="")
    with open(manifest_path, "w") as manifest_file:
        manifest_file.write(processed_output)


def main():
    """Main execution function."""
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Extract chart info from application.yaml, download chart, and run helm template.",
        add_help=True
    )
    parser.add_argument(
        "--workdir",
        type=str,
        help="Working directory containing application.yaml (default: current directory)"
    )
    parser.add_argument(
        "--chart-dir",
        type=str,
        help="Directory to download charts to (default: .chart)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--secrets",
        action="store_true",
        help="Decode base64 values in Secret resources and write to .manifest.secrets.yaml (disabled by default)"
    )

    # Parse known args, keeping unknown ones for helm template
    args, extra_args = parser.parse_known_args()

    verbose = args.verbose
    secrets = args.secrets

    # Resolve paths
    workdir = Path(args.workdir).resolve() if args.workdir else Path.cwd()
    application_yaml_path = workdir / "application.yaml"
    values_file = workdir / "values.yaml"
    chart_dir = Path(args.chart_dir).resolve() if args.chart_dir else workdir / ".chart"
    output_dir = workdir

    log(f"Working directory: {workdir}", verbose)
    log(f"Application YAML: {application_yaml_path}", verbose)

    # Parse application.yaml
    log("Loading application.yaml...", verbose)
    app_yaml = load_application_yaml(application_yaml_path)

    # Extract chart info
    repo_url, chart_name, version, is_git_chart = extract_chart_info(app_yaml)
    log(f"Chart: {chart_name}", verbose)
    log(f"Repository: {repo_url}", verbose)
    log(f"Version: {version}", verbose)
    log(f"Chart type: {'Git' if is_git_chart else 'Helm'}", verbose)

    # Download chart if needed
    download_chart(repo_url, chart_name, version, chart_dir, is_git_chart, verbose)

    # Run helm template
    # For Git charts, chart_name is a path (e.g., "charts/argo-cd"), so get the last component
    # For Helm charts, chart_name is just the chart name
    actual_chart_dir_name = Path(chart_name).name if is_git_chart else chart_name
    chart_path = chart_dir / actual_chart_dir_name
    log("Running helm template...", verbose)
    run_helm_template(chart_path, version, extra_args, values_file, output_dir, secrets, verbose)

    manifest_file = ".manifest.secrets.yaml" if secrets else ".manifest.yaml"
    log(f"Output written to {output_dir / manifest_file}", verbose)


if __name__ == "__main__":
    main()
