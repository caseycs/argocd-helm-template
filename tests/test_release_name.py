"""Test for custom Helm release name rendering using Click CLI."""

import sys
from pathlib import Path

# Add parent directory to path to import the main module
sys.path.insert(0, str(Path(__file__).parent.parent))

from click.testing import CliRunner

from argocd_helm_template import cli


def test_release_name_override():
    """End-to-end test: Render chart with custom release name.

    Tests that custom Helm release names are properly applied:
    1. Invokes 'render' command with release-name test data
    2. Verifies CLI exit code is 0
    3. Verifies YAML output is present
    4. Verifies custom release name appears in output

    The test uses releaseName: release-name-redefined in application.yaml,
    which should appear in the rendered manifests instead of the default
    release name.

    Note: Cache directories are cleaned up automatically by conftest.py pre-hook.

    Tests against: public.ecr.aws/karpenter with custom release name
    """
    runner = CliRunner()
    test_dir = Path(__file__).parent / "release-name"
    chart_dir = test_dir / ".chart"

    # Invoke the render command via Click CLI
    result = runner.invoke(cli, ["render", "--workdir", str(test_dir)])

    # Verify CLI executed successfully (exit code 0)
    assert result.exit_code == 0, f"CLI failed with exit code {result.exit_code}\nOutput:\n{result.output}"

    # Verify YAML output
    assert "---" in result.output, "Output does not contain YAML"

    # Verify custom release name is present in the rendered output
    # The custom releaseName should appear in service account names and labels
    assert "release-name-redefined" in result.output or "release-name-redefined-karpenter" in result.output, \
        "Custom release name 'release-name-redefined' not found in output. This may indicate the helm releaseName is not being applied."

    # Verify Chart.yaml was downloaded
    chart_yaml = chart_dir / "karpenter" / "Chart.yaml"
    assert chart_yaml.exists(), f"Chart.yaml not found at {chart_yaml}"
