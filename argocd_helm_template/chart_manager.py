"""Chart downloading and management utilities."""

import shutil
from pathlib import Path
import yaml
from .argocd_application import ArgocdApplication
from .utils import log, get_helm_repo_name_from_url, get_git_cache_dir, run_command, CommandError, GIT_NON_INTERACTIVE_ENV
from .git_helper import GitRepo


class HelmChartManager:
    """Manages Helm chart downloading and caching."""

    def __init__(self, chart_dir: Path, workdir: Path, verbose: bool = False):
        """
        Initialize HelmChartManager.

        Args:
            chart_dir: Directory to download/store charts
            workdir: Working directory
            verbose: Enable verbose logging
        """
        self.chart_dir = chart_dir
        self.workdir = workdir
        self.verbose = verbose

    def _get_metadata_file(self) -> Path:
        """Get path to metadata file tracking chart source information."""
        return self.chart_dir / ".chart-metadata.yaml"

    def _load_metadata(self) -> dict:
        """Load stored chart metadata. Returns empty dict if file doesn't exist."""
        metadata_file = self._get_metadata_file()
        if not metadata_file.exists():
            return {}

        with open(metadata_file) as f:
            data = yaml.safe_load(f)
            return data or {}

    def _save_metadata(self, repo_url: str, chart_name: str, version: str):
        """Save chart metadata to file."""
        metadata = {
            "repoURL": repo_url,
            "chartName": chart_name,
            "targetRevision": version,
        }
        metadata_file = self._get_metadata_file()
        metadata_file.parent.mkdir(parents=True, exist_ok=True)
        with open(metadata_file, "w") as f:
            yaml.dump(metadata, f, default_flow_style=False)

    def _should_download(self, chart_name: str, version: str, repo_url: str, is_git: bool) -> bool:
        """
        Check if chart needs to be downloaded.

        Returns True if:
        - Chart directory doesn't exist
        - Metadata file doesn't exist (first download)
        - repoURL changed
        - chart/path name changed
        - targetRevision changed
        """
        if is_git:
            # For Git charts, always return True to ensure we re-copy from latest checkout
            return True

        if not self.chart_dir.exists():
            return True

        # Check stored metadata
        stored_metadata = self._load_metadata()

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
                f"targetRevision {stored_metadata.get('targetRevision')} -> {version}"
            )
            return True

        # Additional validation: verify Chart.yaml exists and is readable
        chart_path = self.chart_dir / chart_name
        chart_yaml = chart_path / "Chart.yaml"

        if not chart_path.exists() or not chart_yaml.exists():
            log(f"Chart directory or Chart.yaml missing at {chart_yaml}, re-downloading")
            return True

        return False

    def _clean_chart_dir(self):
        """Remove and recreate the chart directory."""
        if self.chart_dir.exists():
            log(f"Removing existing .chart directory at {self.chart_dir}")
            shutil.rmtree(self.chart_dir)
        self.chart_dir.mkdir(parents=True, exist_ok=True)

    def _symlink_git_chart(self, repo_path: Path, chart_path: str):
        """Create a symlink from the chart directory to the Git repository chart."""
        self._clean_chart_dir()

        # Source path in the Git repo
        source_chart_path = repo_path / chart_path

        if not source_chart_path.exists():
            raise FileNotFoundError(f"Chart not found at {source_chart_path}")

        # Get the chart directory name (last component of the path)
        chart_dir_name = source_chart_path.name

        # Destination symlink path in the .chart directory
        dest_chart_path = self.chart_dir / chart_dir_name

        log(f"Creating symlink from {dest_chart_path} to {source_chart_path}")
        dest_chart_path.symlink_to(source_chart_path)

    def _is_helm_repo_added(self, repo_name: str) -> bool:
        """Check if Helm repository is already added."""
        cmd = ["helm", "repo", "list", "-o", "json"]
        try:
            result = run_command(cmd, verbose=self.verbose, check=False)
        except CommandError:
            return False

        if result.returncode != 0:
            return False

        try:
            repos = yaml.safe_load(result.stdout) or []
            return any(repo.get("name") == repo_name for repo in repos)
        except:
            return False

    def _ensure_helm_repo_added(self, repo_name: str, repo_url: str):
        """Ensure Helm repository is added and updated."""
        if not self._is_helm_repo_added(repo_name):
            log(f"Adding Helm repository {repo_name}...")
            cmd = ["helm", "repo", "add", repo_name, repo_url]
            run_command(cmd, verbose=self.verbose)
        else:
            log(f"Helm repository {repo_name} already added")

        # Update repo to get latest chart info
        log(f"Updating Helm repository {repo_name}...")
        cmd = ["helm", "repo", "update", repo_name]
        run_command(cmd, verbose=self.verbose)

    def _pull_helm_chart(self, repo_url: str, chart_name: str, version: str, is_oci: bool):
        """Download chart using helm pull."""
        self._clean_chart_dir()

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
            "--destination", str(self.chart_dir)
        ]

        run_command(cmd, verbose=self.verbose)

    def _clone_or_get_cached_repo(self, repo_url: str) -> GitRepo:
        """Clone a Git repository to cache directory if it doesn't exist, or return cached."""
        cache_dir = get_git_cache_dir(repo_url, self.workdir)

        if not cache_dir.exists():
            log(f"Cloning repository from {repo_url} to {cache_dir}...")
            cache_dir.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["git", "--no-pager", "clone", repo_url, str(cache_dir)]
            run_command(cmd, verbose=self.verbose, env=GIT_NON_INTERACTIVE_ENV)
        else:
            log(f"Using cached repository at {cache_dir}")

        return GitRepo(cache_dir, verbose=self.verbose)

    def download(self, app: ArgocdApplication) -> Path:
        """
        Download chart and return the path to the chart directory.

        Args:
            app: ArgocdApplication instance (must be validated)

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
        chart_path = self.chart_dir / actual_chart_dir_name

        if not self._should_download(chart_name, version, repo_url, is_git):
            log(f"Chart {chart_name}:{version} already exists in {self.chart_dir}")
            return chart_path

        if is_git:
            # Handle Git-based chart
            log(f"Downloading chart {chart_name} from Git revision {version}...")
            repo = self._clone_or_get_cached_repo(repo_url)
            repo.checkout(version)
            self._symlink_git_chart(repo.path, chart_name)
            # Git charts always re-copy, so no metadata recording needed
        else:
            # Handle Helm registry chart (traditional or OCI)
            is_oci = app.is_helm_oci()

            # Ensure repo is added for non-OCI registries
            if not is_oci:
                repo_name = get_helm_repo_name_from_url(repo_url)
                self._ensure_helm_repo_added(repo_name, repo_url)

            # Determine chart reference based on registry type
            if is_oci:
                chart_ref = repo_url
            else:
                chart_ref = get_helm_repo_name_from_url(repo_url)

            log(f"Downloading chart {chart_name}:{version}...")
            self._pull_helm_chart(chart_ref, chart_name, version, is_oci)

            # Record metadata for future cache validation
            self._save_metadata(repo_url, chart_name, version)

        return chart_path
