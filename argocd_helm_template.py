#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pyyaml",
# ]
# ///

"""
Extract chart info from application.yaml, download chart, and run helm template.
Usage: uv run argocd_helm_template.py [--workdir DIR] [--verbose] [--secrets] [--diff] [additional helm template args]
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


def get_git_cache_dir(repo_url: str, workdir: Path) -> Path:
    """Get the cache directory path for a Git repository in .chart_repo within the working directory."""
    cache_root = workdir / ".chart_repo"
    repo_name = get_repo_name_from_url(repo_url)
    return cache_root / repo_name


def clone_or_update_git_repo(repo_url: str, workdir: Path, verbose: bool = False) -> Path:
    """
    Clone a Git repository in the cache directory if it doesn't exist.

    Returns:
        Path to the cached repository
    """
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


def download_chart(repo_url: str, chart_name: str, version: str, chart_dir: Path, workdir: Path, is_git: bool = False, verbose: bool = False):
    """Wrapper that checks if download is needed and downloads chart."""
    if not should_download_chart(chart_dir, chart_name, version, is_git):
        log(f"Chart {chart_name}:{version} already exists in {chart_dir}", verbose)
        return

    if is_git:
        # Handle Git-based chart
        log(f"Downloading chart {chart_name} from Git revision {version}...", verbose)
        repo_path = clone_or_update_git_repo(repo_url, workdir, verbose)
        checkout_git_revision(repo_path, version, verbose)
        _symlink_git_chart(repo_path, chart_name, chart_dir, verbose)
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


def run_helm_template(chart_path: Path, version: str, extra_args: list[str], values_file: Path = Path("values.yaml"), output_dir: Path = Path("."), secrets: bool = False, verbose: bool = False, print_output: bool = True):
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

    # Write processed output to manifest file
    with open(manifest_path, "w") as manifest_file:
        manifest_file.write(processed_output)

    # Print to stdout only if print_output is True
    if print_output:
        print(processed_output, end="")


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


def render_manifests(workdir: Path, chart_dir: Path, application_yaml_path: Path, values_file: Path, output_dir: Path, extra_args: list[str], secrets: bool = False, verbose: bool = False, print_output: bool = True):
    """
    Load application.yaml, extract chart info, download chart, and render manifests.

    Args:
        workdir: Working directory
        chart_dir: Directory to download/store charts
        application_yaml_path: Path to application.yaml
        values_file: Path to values.yaml
        output_dir: Directory to write manifests to
        extra_args: Additional helm template arguments
        secrets: Whether to decode base64 in Secrets
        verbose: Enable verbose logging
        print_output: Whether to print output to stdout
    """
    log(f"Loading {application_yaml_path}...", verbose)
    app_yaml = load_application_yaml(application_yaml_path)

    # Extract chart info
    repo_url, chart_name, version, is_git_chart = extract_chart_info(app_yaml)
    log(f"Chart: {chart_name}", verbose)
    log(f"Repository: {repo_url}", verbose)
    log(f"Version: {version}", verbose)
    log(f"Chart type: {'Git' if is_git_chart else 'Helm'}", verbose)

    # Download chart if needed
    download_chart(repo_url, chart_name, version, chart_dir, workdir, is_git_chart, verbose)

    # Run helm template
    # For Git charts, chart_name is a path (e.g., "charts/argo-cd"), so get the last component
    # For Helm charts, chart_name is just the chart name
    actual_chart_dir_name = Path(chart_name).name if is_git_chart else chart_name
    chart_path = chart_dir / actual_chart_dir_name
    log("Running helm template...", verbose)
    run_helm_template(chart_path, version, extra_args, values_file, output_dir, secrets, verbose, print_output)

    manifest_file = ".manifest.secrets.yaml" if secrets else ".manifest.yaml"
    log(f"Output written to {output_dir / manifest_file}", verbose)


def diff_mode(workdir: Path, chart_dir: Path, diff_ref: str, application_file: str, extra_args: list[str], secrets: bool = False, verbose: bool = False, diff_sort: bool = False):
    """
    Generate manifests from both git-committed and current state of application file and values.yaml.

    Args:
        workdir: Working directory
        chart_dir: Directory for charts
        diff_ref: Git reference to diff against (default: HEAD, can be origin/main, --cached, etc.)
        application_file: Application YAML filename
        extra_args: Additional helm template arguments
        secrets: Whether to decode base64 in Secrets
        verbose: Enable verbose logging
        diff_sort: Sort YAML keys alphabetically before showing diff
    """
    # 1. Check if git repo
    if not check_git_repo(workdir, verbose):
        print("Error: Working directory is not part of a git repository", file=sys.stderr)
        sys.exit(1)

    log("Verified workdir is in a git repository", verbose)

    # 2. Check for changes
    files_to_check = [application_file, "values.yaml"]
    if not check_file_changes(workdir, files_to_check, verbose):
        print(f"Error: No changes detected in {application_file} or values.yaml", file=sys.stderr)
        sys.exit(1)

    log(f"Detected changes in {application_file} or values.yaml", verbose)

    # 3. Create .diff directory
    diff_dir = workdir / ".diff"
    if diff_dir.exists():
        log(f"Removing existing .diff directory at {diff_dir}", verbose)
        shutil.rmtree(diff_dir)
    diff_dir.mkdir(parents=True, exist_ok=True)
    log(f"Created .diff directory at {diff_dir}", verbose)

    # 4. Extract original files from git
    for filename in files_to_check:
        try:
            log(f"Extracting {filename} from git {diff_ref}...", verbose)
            extract_git_file(workdir, filename, diff_dir / filename, diff_ref, verbose)
        except Exception as e:
            print(f"Error: Could not extract {filename} from git: {e}", file=sys.stderr)
            sys.exit(1)

    log("Successfully extracted files from git", verbose)

    # 5. Render original manifests (from .diff/)
    log("Rendering manifests from original (committed) files...", verbose)
    render_manifests(
        workdir=workdir,
        chart_dir=chart_dir,
        application_yaml_path=diff_dir / application_file,
        values_file=diff_dir / "values.yaml",
        output_dir=diff_dir,
        extra_args=extra_args,
        secrets=secrets,
        verbose=verbose,
        print_output=False
    )

    # 6. Render current manifests (to ./)
    log("Rendering manifests from current files...", verbose)
    render_manifests(
        workdir=workdir,
        chart_dir=chart_dir,
        application_yaml_path=workdir / application_file,
        values_file=workdir / "values.yaml",
        output_dir=workdir,
        extra_args=extra_args,
        secrets=secrets,
        verbose=verbose,
        print_output=False
    )

    # Sort manifests if requested
    if diff_sort:
        log("Sorting YAML keys in manifest files before diff...", verbose)
        sort_yaml_file(diff_dir / ".manifest.yaml", verbose)
        sort_yaml_file(workdir / ".manifest.yaml", verbose)

    log(f"Diff complete (comparing against {diff_ref}). Showing diff...", verbose)

    # Execute git diff in interactive mode to show differences
    diff_cmd = ["git", "diff", "--no-index", "--", str(diff_dir / ".manifest.yaml"), str(workdir / ".manifest.yaml")]
    log(f"Running: {' '.join(diff_cmd)}", verbose)
    subprocess.run(diff_cmd)


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
        help="Working directory containing application file and values.yaml (default: current directory)"
    )
    parser.add_argument(
        "--application",
        type=str,
        default="application.yaml",
        help="Application YAML filename (default: application.yaml)"
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
    parser.add_argument(
        "--diff",
        type=str,
        default=None,
        const="HEAD",
        nargs="?",
        help="Generate diff between current and specified git ref (default: HEAD, hint: origin/main or --cached)"
    )
    parser.add_argument(
        "--diff-sort",
        action="store_true",
        help="Sort YAML keys alphabetically before showing diff"
    )

    # Parse known args, keeping unknown ones for helm template
    args, extra_args = parser.parse_known_args()

    verbose = args.verbose
    secrets = args.secrets

    # Resolve paths
    workdir = Path(args.workdir).resolve() if args.workdir else Path.cwd()
    chart_dir = Path(args.chart_dir).resolve() if args.chart_dir else workdir / ".chart"

    log(f"Working directory: {workdir}", verbose)

    # Mode dispatcher - handle --diff mode early
    if args.diff is not None:
        diff_mode(workdir, chart_dir, args.diff, args.application, extra_args, secrets, verbose, args.diff_sort)
        return

    # Normal mode - continue with standard template generation
    application_yaml_path = workdir / args.application
    values_file = workdir / "values.yaml"
    output_dir = workdir

    log(f"Application YAML: {application_yaml_path}", verbose)

    # Render manifests using common function
    render_manifests(
        workdir=workdir,
        chart_dir=chart_dir,
        application_yaml_path=application_yaml_path,
        values_file=values_file,
        output_dir=output_dir,
        extra_args=extra_args,
        secrets=secrets,
        verbose=verbose,
        print_output=True
    )


if __name__ == "__main__":
    main()
