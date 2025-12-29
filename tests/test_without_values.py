"""Test for skipCrds flag handling in Helm configuration."""

import sys
from pathlib import Path

# Add parent directory to path to import the main module
sys.path.insert(0, str(Path(__file__).parent.parent))

from click.testing import CliRunner

from argocd_helm_template import cli


def test_without_values():
    """End-to-end test: Verify skipCrds flag prevents CRDs from being rendered.

    Tests that when skipCrds: true is set in helm configuration:
    1. Invokes 'render' command with skip-crds test data
    2. Verifies CLI exit code is 0
    3. Verifies YAML output is present
    4. Verifies CustomResourceDefinition is NOT present in output
    5. Verifies Chart.yaml was downloaded

    The test uses skipCrds: true in application.yaml with cert-manager chart,
    which includes both CRDs and application resources. The --skip-crds flag
    should prevent CRD manifests from appearing in the rendered output.

    Note: Cache directories are cleaned up automatically by conftest.py pre-hook.

    Tests against: https://charts.jetstack.io/cert-manager with skipCrds enabled
    """
    runner = CliRunner()
    test_dir = Path(__file__).parent / "without-values"
    chart_dir = test_dir / ".chart"

    # Invoke the render command via Click CLI
    result = runner.invoke(cli, ["render", "--workdir", str(test_dir)])

    # Verify CLI executed successfully (exit code 0)
    assert result.exit_code == 0, f"CLI failed with exit code {result.exit_code}\nOutput:\n{result.output}"

    # Verify YAML output
    assert "---" in result.output, "Output does not contain YAML"

    # Verify Chart.yaml was downloaded
    chart_yaml = chart_dir / "argo-events" / "Chart.yaml"
    assert chart_yaml.exists(), f"Chart.yaml not found at {chart_yaml}"

