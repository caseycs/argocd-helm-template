"""Helm template execution and manifest processing utilities."""

import base64
import subprocess
from pathlib import Path
import yaml

from .utils import log
from .argocd_application import ArgocdApplication
from .ref_mapper import build_ref_mapping, apply_ref_mapping_to_value_files

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
                log(f"Processing Secret: {doc.get('metadata', {}).get('name', 'unknown')}")

                # Decode data section
                if 'data' in doc and isinstance(doc['data'], dict):
                    for key, value in doc['data'].items():
                        if isinstance(value, str):
                            try:
                                decoded = base64.b64decode(value).decode('utf-8')
                                # Wrap in LiteralString to force literal block scalar style
                                doc['data'][key] = LiteralString(decoded)
                                log(f"  Decoded key: {key}")
                            except Exception as e:
                                log(f"  Failed to decode key {key}: {e}")
                                # Keep original value if decoding fails
                                pass

            documents.append(doc)
    except yaml.YAMLError as e:
        log(f"Warning: Failed to parse YAML: {e}")
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


# --- Helm Template Execution ---

def run_helm_template(chart_path: Path, helm_args: list[str], output_dir: Path = Path("."), secrets: bool = False, verbose: bool = False, print_output: bool = True):
    """
    Run helm template command with computed helm arguments and optionally post-process Secrets.

    Args:
        chart_path: Path to helm chart
        helm_args: Helm arguments from compute_helm_args (release name, values files, skipCrds, etc)
        output_dir: Directory to write manifests
        secrets: Whether to decode base64 in Secrets
        verbose: Enable verbose logging
        print_output: Whether to print output to stdout
    """
    # Build the helm template command
    # Syntax: helm template [NAME] [CHART] [flags]
    # NAME is optional (release name), CHART is the chart path
    cmd = ["helm", "template"]

    # Add helm arguments from compute_helm_args (includes release name, values files, skipCrds, etc)
    cmd.extend(helm_args)

    # Add chart path
    cmd.append(str(chart_path))

    # Show command only in verbose mode
    if verbose:
        log(f"Running: {' '.join(cmd)}")

    # Run helm template and capture output
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    stdout_output, stderr_output = process.communicate()

    if process.returncode != 0:
        # Show both stdout and stderr on error
        error_parts = [f"Helm template execution failed with exit code {process.returncode}:"]
        if stdout_output:
            error_parts.append(f"stdout:\n{stdout_output}")
        if stderr_output:
            error_parts.append(f"stderr:\n{stderr_output}")
        raise RuntimeError("\n".join(error_parts))
    elif verbose and stderr_output:
        log(f"stderr:\n{stderr_output}")

    # Post-process to decode Secret values if requested
    if secrets:
        log("Post-processing Secrets to decode base64 values...")
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


def compute_helm_args(app: ArgocdApplication, workdir: Path, ref_map_override: dict = None, verbose: bool = False) -> list[str]:
    """
    Compute helm template command-line arguments from ArgocdApplication.

    Processes:
    - Helm parameters: releaseName (with fallback to metadata.name), skipCrds
    - Sources: create ref name => repoUrl dict
    - Mapping: determine workdir repo root (if mapping not defined), validate all refs are mapped
    - Value files: apply ref mapping and resolve paths

    Args:
        app: Validated ArgocdApplication instance
        workdir: Working directory
        ref_map_override: Optional mapping of ref names to local paths
        verbose: Enable verbose logging

    Returns:
        list[str]: Command-line arguments for helm template command.
                   Includes release name, -f arguments for values files,
                   and --skip-crds flag (if enabled).

    Raises:
        AssertionError: If ArgocdApplication is not validated
        RuntimeError: If mapping is incomplete or invalid
    """
    # Internal check: application must be already validated
    try:
        app.validate()
    except ValueError as e:
        assert False, f"Validated ArgoCD application expected: {str(e)}"

    # Extract helm parameters: use releaseName from helm config, fallback to metadata.name
    release_name = app.get_helm_release_name() or app.get_app_name()

    # Build arguments array, add release name
    args = ['--release-name', release_name]

    # Add skipCrds flag if enabled
    if app.get_helm_skip_crds():
        args.append("--skip-crds")

    # Extract ref sources and build mapping
    ref_sources = app.get_all_ref_sources()
    ref_map_override = ref_map_override or {}

    # Build ref mapping
    ref_mapping = build_ref_mapping(ref_sources, workdir, ref_map_override, verbose)

    # Process value files with ref mapping
    value_files_list = app.get_helm_value_files()
    values_files = []

    if value_files_list:
        values_files = apply_ref_mapping_to_value_files(value_files_list, ref_mapping, verbose)

    # Add values files
    for values_file in values_files:
        args.extend(["-f", str(values_file)])

    return args


def render_manifests(
    workdir: Path,
    chart_dir: Path,
    application_yaml_path: Path,
    output_dir: Path,
    extra_args: list[str],
    ref_map_override: dict = None,
    secrets: bool = False,
    verbose: bool = False,
    print_output: bool = True
):
    """
    Load application.yaml, validate, extract chart info, download chart, and render manifests.

    Args:
        workdir: Working directory
        chart_dir: Directory to download/store charts
        application_yaml_path: Path to application.yaml
        output_dir: Directory to write manifests to
        extra_args: Additional helm template arguments
        ref_map_override: Optional mapping of ref names to local paths
        secrets: Whether to decode base64 in Secrets
        verbose: Enable verbose logging
        print_output: Whether to print output to stdout

    Raises:
        RuntimeError: If application is invalid or rendering fails
    """
    # Import here to avoid circular dependency
    from .chart_manager import HelmChartManager

    log(f"Loading {application_yaml_path}...")
    app = ArgocdApplication.load(application_yaml_path)

    # Validate application
    app.validate()

    # Log chart source info
    chart_source = app.get_helm_chart_source()
    chart_name = chart_source.get("chart" if app.is_helm_repo() else "path", "")
    repo_url = chart_source.get("repoURL", "")
    version = chart_source.get("targetRevision", "").lstrip("v")
    is_git_chart = app.is_helm_git()

    log(f"Chart: {chart_name}")
    log(f"Repository: {repo_url}")
    log(f"Version: {version}")
    log(f"Chart type: {'Git' if is_git_chart else 'Helm'}")

    # Download chart if needed and get the chart path
    chart_manager = HelmChartManager(chart_dir, workdir, verbose)
    chart_path = chart_manager.download(app)

    # Compute helm arguments (includes release name, values files, skipCrds)
    helm_args = compute_helm_args(app, workdir, ref_map_override, verbose)

    # Merge with extra_args
    helm_args.extend(extra_args)

    # Run helm template
    log("Running helm template...")
    run_helm_template(chart_path, helm_args, output_dir, secrets, verbose, print_output)

    manifest_file = ".manifest.secrets.yaml" if secrets else ".manifest.yaml"
    log(f"Output written to {output_dir / manifest_file}")
