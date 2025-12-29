"""Test for multiple values files support."""

import sys
from pathlib import Path

# Add parent directory to path to import the main module
sys.path.insert(0, str(Path(__file__).parent.parent))

from click.testing import CliRunner

from argocd_helm_template import cli


def test_multiple_values_files_render():
    """End-to-end test: Render chart with multiple values files.

    Tests that multiple values files specified in helm.valueFiles are all passed
    to helm template with -f arguments:
    1. Invokes 'render' command with multiple-values test data
    2. Verifies CLI exit code is 0
    3. Verifies YAML output is present
    4. Verifies Chart.yaml was downloaded

    The test uses valueFiles with $values/ ref mapping to multiple local files.

    Note: Cache directories are cleaned up automatically by conftest.py pre-hook.

    Tests against: public.ecr.aws/karpenter with multiple values files
    """
    runner = CliRunner()
    test_dir = Path(__file__).parent / "multiple-values"
    chart_dir = test_dir / ".chart"

    # Invoke the render command via Click CLI
    result = runner.invoke(cli, ["render", "--workdir", str(test_dir), "--verbose"])

    # Verify CLI executed successfully (exit code 0)
    assert result.exit_code == 0, f"CLI failed with exit code {result.exit_code}\nOutput:\n{result.output}"

    # Verify YAML output
    assert "---" in result.output, "Output does not contain YAML"

    # Verify both values files were used in the helm command
    assert "app.kubernetes.io/name: another-karpenter" in result.output, "No another-karpenter (from values1.yaml) flag found in output"
    assert 'value: "another-cluster-name"' in result.output, "No another-cluster-name (from values2.yaml) found in output"

    # Verify Chart.yaml was downloaded
    chart_yaml = chart_dir / "karpenter" / "Chart.yaml"
    assert chart_yaml.exists(), f"Chart.yaml not found at {chart_yaml}"
