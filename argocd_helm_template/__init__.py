"""
ArgoCD Helm Template - Render Helm charts from ArgoCD applications.
Supports rendering Kubernetes manifests from ArgoCD application definitions.
"""

from pathlib import Path
import click

from .utils import log
from .helm_helper import render_manifests

__version__ = "0.1.0"


class KeyValueParamType(click.ParamType):
    """Custom Click parameter type for key=value pairs."""
    name = "key_value"

    def convert(self, value, param, ctx):
        if '=' not in value:
            self.fail(f'{value} is not a valid key=value pair', param, ctx)
        key, val = value.split('=', 1)
        return (key.strip(), val.strip())


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

      argocd-helm-template render --skip-crds --namespace myapp --release-name myrelese
    """
    extra_args = list(ctx.args)

    # Resolve paths
    workdir = workdir.resolve() if workdir else Path.cwd()
    chart_dir = chart_dir.resolve() if chart_dir else workdir / ".chart"

    log(f"Working directory: {workdir}")

    # Convert ref_map tuple to dictionary
    ref_map_override = {}
    if ref_map:
        for ref_name, local_path in ref_map:
            ref_map_override[ref_name] = local_path
            log(f"Ref map parameter: {ref_name} -> {local_path}")

    # Render manifests using common function
    application_yaml_path = workdir / application
    output_dir = workdir

    log(f"Application YAML: {application_yaml_path}")

    try:
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
    except RuntimeError as e:
        raise click.ClickException(str(e))


__all__ = ["cli", "render_manifests"]
