"""
ArgocdApplication class to encapsulate and provide type-safe access to
ArgoCD Application YAML data without exposing raw dictionaries.

This is a design document. The class is not yet integrated into the main code.
Raw YAML data is never exposed directly to clients.
"""

from typing import Optional


class ArgocdApplication:
    """
    Encapsulates ArgoCD Application YAML data with methods to check
    chart type and extract configuration.

    Raw YAML dictionary is private and never exposed.
    """

    def __init__(self, yaml_dict: dict):
        """
        Initialize with parsed YAML dictionary.

        Args:
            yaml_dict: Dictionary from load_application_yaml() or yaml.safe_load()

        Raises:
            ValueError: If YAML structure is invalid
        """
        if not isinstance(yaml_dict, dict):
            raise ValueError("yaml_dict must be a dictionary")

        self._data = yaml_dict
        self._validate_structure()

    def _validate_structure(self) -> None:
        """Validate that required YAML structure exists."""
        if "spec" not in self._data:
            raise ValueError("Invalid application.yaml: missing 'spec' section")

        spec = self._data.get("spec", {})

        # Support both 'sources' (plural, modern) and 'source' (singular, legacy)
        if "sources" not in spec and "source" not in spec:
            raise ValueError("Invalid application.yaml: missing 'sources' or 'source' in spec")

        # Normalize: convert singular 'source' to plural 'sources' for internal consistency
        if "source" in spec and "sources" not in spec:
            source = spec.get("source")
            if isinstance(source, dict):
                # Convert single source to sources list
                self._data["spec"]["sources"] = [source]
            else:
                raise ValueError("Invalid application.yaml: 'source' must be a dict")

        # Validate sources is a list
        sources = self._data.get("spec", {}).get("sources", [])
        if not isinstance(sources, list):
            raise ValueError("Invalid application.yaml: 'sources' must be a list")

    # ========== Chart Type Checks (Internal) ==========

    def _is_helm_repo(self, source: dict) -> bool:
        """
        Check if a source is a Helm repository chart.

        A Helm repository chart requires:
        - chart: Chart name (required)

        And MUST NOT have:
        - path (conflicts with Helm repo)
        - ref (conflicts with Helm repo)

        Args:
            source: Source dict to check

        Returns:
            True if source is a valid Helm repo chart, False otherwise
        """
        return (
            "chart" in source
            and "path" not in source
            and "ref" not in source
        )

    def _is_helm_oci(self, source: dict) -> bool:
        """
        Check if a source is from OCI registry (Helm repo without http/https prefix).

        OCI registry URLs look like:
        - docker.io/myrepo/mychart
        - ghcr.io/myorg/mychart
        - ecr.aws/org/chart

        A Helm OCI chart requires:
        - chart: Chart name (required)
        - repoURL: OCI registry URL without http/https prefix (required)

        And MUST NOT have:
        - path (conflicts with Helm repo)
        - ref (conflicts with Helm repo)

        Args:
            source: Source dict to check

        Returns:
            True if source is a valid OCI registry chart, False otherwise
        """
        if not self._is_helm_repo(source):
            return False

        repo_url = source.get("repoURL", "")
        # OCI registry URLs don't start with http:// or https://
        return not repo_url.startswith(("http://", "https://"))

    def _is_helm_git(self, source: dict) -> bool:
        """
        Check if a source is a Git-based Helm chart.

        A Git-based Helm chart requires:
        - path: Path to chart within repository (required)
        - helm: Helm configuration section (required)

        And MUST NOT have:
        - chart (conflicts with Git path)
        - ref (conflicts with Git path)

        Args:
            source: Source dict to check

        Returns:
            True if source is a valid Git-based Helm chart, False otherwise
        """
        return (
            "path" in source
            and "helm" in source
            and "chart" not in source
            and "ref" not in source
        )

    def _is_ref(self, source: dict) -> bool:
        """
        Check if a source is a reference source.

        A reference source provides values for other Helm sources.

        A reference source requires:
        - ref: Reference name (required)

        And MUST NOT have:
        - chart (conflicts with ref)
        - path (conflicts with ref)
        - helm (conflicts with ref)

        Args:
            source: Source dict to check

        Returns:
            True if source is a valid reference source, False otherwise
        """
        return (
            "ref" in source
            and "chart" not in source
            and "path" not in source
            and "helm" not in source
        )

    # ========== Public Chart Type Checks (for backward compatibility) ==========

    def is_helm_repo(self) -> bool:
        """
        Check if application uses a Helm repository chart.

        Returns:
            True if any source is a Helm repo chart, False otherwise
        """
        sources = self._data.get("spec", {}).get("sources", [])
        for source in sources:
            if self._is_helm_repo(source):
                return True
        return False

    def is_helm_oci(self) -> bool:
        """
        Check if application uses an OCI registry Helm chart.

        Returns:
            True if any source is an OCI registry chart, False otherwise
        """
        sources = self._data.get("spec", {}).get("sources", [])
        for source in sources:
            if self._is_helm_oci(source):
                return True
        return False

    def is_helm_git(self) -> bool:
        """
        Check if application uses a Git-based Helm chart.

        Returns:
            True if any source is a Git-based Helm chart, False otherwise
        """
        sources = self._data.get("spec", {}).get("sources", [])
        for source in sources:
            if self._is_helm_git(source):
                return True
        return False

    # ========== Metadata Access ==========

    def get_app_name(self) -> str:
        """Get application name from metadata.name."""
        return self._data.get("metadata", {}).get("name", "")

    def get_app_namespace(self) -> str:
        """Get application namespace from metadata.namespace."""
        return self._data.get("metadata", {}).get("namespace", "")

    # ========== Source Information ==========

    def get_chart_source(self) -> Optional[dict]:
        """
        Get the source that contains chart information (read-only copy).

        The chart source is the one with either 'chart' or 'path' field.

        Returns:
            Copy of chart source dict, or None if not found
        """
        sources = self._data.get("spec", {}).get("sources", [])
        for source in sources:
            if "chart" in source or "path" in source:
                return dict(source)
        return None

    def get_helm_source(self) -> Optional[dict]:
        """
        Get the source that contains helm configuration (read-only copy).

        The helm source is the one with 'helm' field.

        Returns:
            Copy of helm source dict, or None if not found
        """
        sources = self._data.get("spec", {}).get("sources", [])
        for source in sources:
            if "helm" in source:
                return dict(source)
        return None

    def get_all_ref_sources(self) -> dict:
        """
        Get all sources with 'ref' field as mapping: ref_name -> repoURL.

        Returns:
            dict: {"ref_name": "repo_url", ...}
            Example: {"values": "https://github.com/org/values-repo"}
        """
        sources = self._data.get("spec", {}).get("sources", [])
        ref_sources = {}

        for source in sources:
            if "ref" in source:
                ref_name = source.get("ref")
                repo_url = source.get("repoURL", "")
                if ref_name and repo_url:
                    ref_sources[ref_name] = repo_url

        return ref_sources

    # ========== Helm Configuration ==========

    def get_helm_release_name(self) -> str:
        """
        Get helm release name.

        If helm config doesn't specify releaseName, returns empty string.
        Caller should fallback to app name if needed.

        Returns:
            Release name string, or empty string if not set
        """
        helm_source = self.get_helm_source()
        if helm_source and "helm" in helm_source:
            return helm_source["helm"].get("releaseName", "")
        return ""

    def get_helm_skip_crds(self) -> bool:
        """
        Get helm skipCrds flag.

        Returns:
            True if skipCrds should be enabled, False by default
        """
        helm_source = self.get_helm_source()
        if helm_source and "helm" in helm_source:
            return helm_source["helm"].get("skipCrds", False)
        return False

    def get_helm_value_files(self) -> list[str]:
        """
        Get helm valueFiles list.

        Returns:
            List of value file paths, or empty list if not defined
        """
        helm_source = self.get_helm_source()
        if helm_source and "helm" in helm_source:
            value_files = helm_source["helm"].get("valueFiles", [])
            return list(value_files)  # Return copy
        return []

    def has_helm_config(self) -> bool:
        """Check if helm configuration exists."""
        return self.get_helm_source() is not None

    # ========== Validation ==========

    def validate(self) -> None:
        """
        Validate application configuration.

        Raises:
            ValueError: If validation fails on first error
        """
        # Check that kind is Application
        kind = self._data.get("kind", "")
        if kind != "Application":
            raise ValueError(
                f"Invalid resource kind: 'Application' expected, got '{kind}'"
            )

        # Check for duplicate ref sources
        ref_sources = self.get_all_ref_sources()
        ref_names = [source.get("ref") for source in self._data.get("spec", {}).get("sources", []) if "ref" in source]
        if len(ref_names) != len(set(ref_names)):
            # Find duplicates
            seen = set()
            duplicates = set()
            for ref in ref_names:
                if ref in seen:
                    duplicates.add(ref)
                seen.add(ref)
            raise ValueError(
                f"Duplicate ref sources found: {', '.join(sorted(duplicates))}"
            )

        # Validate each source individually
        sources = self._data.get("spec", {}).get("sources", [])
        helm_source_indices = []

        for i, source in enumerate(sources):
            # Check if source is a Helm chart definition
            is_helm_chart = self._is_helm_repo(source) or self._is_helm_git(source)
            is_ref_source = self._is_ref(source)

            if is_helm_chart:
                helm_source_indices.append(i)
            elif not is_ref_source:
                # Source must be either helm chart or ref source
                raise ValueError(
                    f"Source is invalid: must be either a Helm chart "
                    "(with 'chart' or 'path'+'helm') or a reference source (with 'ref')"
                )

        # Check that exactly one helm source exists
        if len(helm_source_indices) == 0:
            raise ValueError(
                "Application does not use Helm: no Helm chart source found"
            )
        elif len(helm_source_indices) > 1:
            raise ValueError(
                f"Multiple Helm charts found: sources {helm_source_indices} define Helm charts. "
                "Only one Helm chart per application is supported."
            )

        # Check valueFiles consistency with ref sources
        value_files = self.get_helm_value_files()
        ref_sources = self.get_all_ref_sources()

        if ref_sources and value_files:
            # If ref sources exist, all value files must use ref syntax
            for vf in value_files:
                if vf.startswith("$"):
                    # Extract ref name
                    parts = vf[1:].split("/", 1)
                    if len(parts) == 2:
                        ref_name = parts[0]
                        if ref_name not in ref_sources:
                            raise ValueError(
                                f"valueFile '{vf}' references undefined ref '{ref_name}'. "
                                f"Available refs: {', '.join(ref_sources.keys())}"
                            )
                    else :
                        raise ValueError(f"Error: valueFile '{vf}', ref/path expected but not found")
                else:
                    # No $ prefix when ref sources exist
                    raise ValueError(
                        f"valueFile '{vf}' must use ref prefix (e.g., $ref_name/path) "
                        f"when ref sources are defined"
                    )

    # ========== Internal Representation (Debugging) ==========

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        chart_type = "unknown"
        if self.is_helm_oci():
            chart_type = "helm-oci"
        elif self.is_helm_repo():
            chart_type = "helm-repo"
        elif self.is_helm_git():
            chart_type = "git"

        return (
            f"ArgocdApplication(name={self.get_app_name()!r}, "
            f"type={chart_type}, "
            f"has_helm_config={self.has_helm_config()})"
        )
