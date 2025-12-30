"""
ArgoCD Helm Template - Render Helm charts from ArgoCD applications.
Supports rendering Kubernetes manifests from ArgoCD application definitions.
"""

from pathlib import Path
import yaml
import click

from .argocd_application import ArgocdApplication
from .utils import log
from .chart_manager import download_chart
from .helm_executor import run_helm_template
from .ref_mapper import build_ref_mapping, apply_ref_mapping_to_value_files

__version__ = "0.1.0"


class KeyValueParamType(click.ParamType):
    """Custom Click parameter type for key=value pairs."""
    name = "key_value"

    def convert(self, value, param, ctx):
        if '=' not in value:
            self.fail(f'{value} is not a valid key=value pair', param, ctx)
        key, val = value.split('=', 1)
        return (key.strip(), val.strip())


def load_application_yaml(path: Path = Path("application.yaml")) -> ArgocdApplication:
    """
    Load and parse the application.yaml file.

    Returns:
        ArgocdApplication: Validated ArgoCD application instance

    Raises:
        ValueError: If application.yaml is invalid
    """
    with open(path) as f:
        yaml_dict = yaml.safe_load(f)
    return ArgocdApplication(yaml_dict)


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
        click.ClickException: If mapping is incomplete or invalid
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
    try:
        ref_mapping = build_ref_mapping(ref_sources, workdir, ref_map_override, verbose)
    except RuntimeError as e:
        raise click.ClickException(str(e))

    # Process value files with ref mapping
    value_files_list = app.get_helm_value_files()
    values_files = []

    if value_files_list:
        try:
            values_files = apply_ref_mapping_to_value_files(value_files_list, ref_mapping, verbose)
        except RuntimeError as e:
            raise click.ClickException(str(e))

    # Add values files
    for values_file in values_files:
        args.extend(["-f", str(values_file)])

    return args


def render_manifests(workdir: Path, chart_dir: Path, application_yaml_path: Path, output_dir: Path, extra_args: list[str], ref_map_override: dict = None, secrets: bool = False, verbose: bool = False, print_output: bool = True):
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
    """
    log(f"Loading {application_yaml_path}...", verbose)
    app = load_application_yaml(application_yaml_path)

    # Validate application
    try:
        app.validate()
    except ValueError as e:
        raise click.ClickException(f"Invalid application.yaml: {str(e)}")

    # Log chart source info
    chart_source = app.get_chart_source()
    chart_name = chart_source.get("chart" if app.is_helm_repo() else "path", "")
    repo_url = chart_source.get("repoURL", "")
    version = chart_source.get("targetRevision", "").lstrip("v")
    is_git_chart = app.is_helm_git()

    log(f"Chart: {chart_name}", verbose)
    log(f"Repository: {repo_url}", verbose)
    log(f"Version: {version}", verbose)
    log(f"Chart type: {'Git' if is_git_chart else 'Helm'}", verbose)

    # Download chart if needed and get the chart path
    chart_path = download_chart(app, chart_dir, workdir, verbose)

    # Compute helm arguments (includes release name, values files, skipCrds)
    helm_args = compute_helm_args(app, workdir, ref_map_override, verbose)

    # Merge with extra_args
    helm_args.extend(extra_args)

    # Run helm template
    log("Running helm template...", verbose)
    run_helm_template(chart_path, helm_args, output_dir, secrets, verbose, print_output)

    manifest_file = ".manifest.secrets.yaml" if secrets else ".manifest.yaml"
    log(f"Output written to {output_dir / manifest_file}", verbose)


@click.group()
@click.version_option(version=__version__, prog_name='argocd-helm-template')
def cli():
    """ArgoCD Helm Template - Render Helm charts from ArgoCD applications.

    Extract chart information from application.yaml, download charts, and render
    Kubernetes manifests using helm template.
    """
    pass


@cli.command(context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.option(
    '--workdir',
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help='Working directory containing application file and values.yaml (default: current directory)'
)
@click.option(
    '--application',
    default='application.yaml',
    help='Application YAML filename (default: application.yaml)'
)
@click.option(
    '--chart-dir',
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help='Directory to download charts to (default: .chart)'
)
@click.option(
    '--verbose',
    is_flag=True,
    help='Enable verbose output'
)
@click.option(
    '--secrets',
    is_flag=True,
    help='Decode base64 values in Secret resources and write to .manifest.secrets.yaml'
)
@click.option(
    '--ref-map',
    multiple=True,
    type=KeyValueParamType(),
    help='Map ref sources to local paths (use multiple times: --ref-map ref1=path1 --ref-map ref2=path2). If not provided, uses workdir git root for the first one.'
)
@click.pass_context
def render(ctx, workdir, application, chart_dir, verbose, secrets, ref_map):
    """Render Kubernetes manifests from application.yaml.

    Any additional arguments are passed through to 'helm template'.

    Examples:

      argocd-helm-template render

      argocd-helm-template render --verbose --secrets

      argocd-helm-template render --namespace myapp
    """
    extra_args = list(ctx.args)

    # Resolve paths
    workdir = workdir.resolve() if workdir else Path.cwd()
    chart_dir = chart_dir.resolve() if chart_dir else workdir / ".chart"

    log(f"Working directory: {workdir}", verbose)

    # Convert ref_map tuple to dictionary
    ref_map_override = {}
    if ref_map:
        for ref_name, local_path in ref_map:
            ref_map_override[ref_name] = local_path
            log(f"Ref map parameter: {ref_name} -> {local_path}", verbose)

    # Render manifests using common function
    application_yaml_path = workdir / application
    output_dir = workdir

    log(f"Application YAML: {application_yaml_path}", verbose)

    render_manifests(
        workdir=workdir,
        chart_dir=chart_dir,
        application_yaml_path=application_yaml_path,
        output_dir=output_dir,
        extra_args=extra_args,
        ref_map_override=ref_map_override,
        secrets=secrets,
        verbose=verbose,
        print_output=True
    )


__all__ = ["cli", "load_application_yaml", "compute_helm_args", "render_manifests"]
