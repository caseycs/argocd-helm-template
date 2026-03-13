"""Test for Helm chart rendering without values files."""

import sys
from pathlib import Path

# Add parent directory to path to import the main module
sys.path.insert(0, str(Path(__file__).parent.parent))

from click.testing import CliRunner

from argocd_helm_template import cli
from ._utils import cleanup_test_dir


def test_without_values():
    """End-to-end test: Verify charts render without values files.

    Tests that charts can render successfully even when no values files are specified:
    1. Invokes 'render' command with without-values test data
    2. Verifies CLI exit code is 0
    3. Verifies YAML output is present
    4. Verifies Chart.yaml was downloaded

    The test verifies that valueFiles is optional in helm configuration.

    Tests against: Git-based chart without values files
    """
    test_dir = Path(__file__).parent / "without-values"
    cleanup_test_dir(test_dir)

    runner = CliRunner()
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


def test_skip_output():
    """End-to-end test: Verify --skip-output writes .manifest.yaml but prints nothing to stdout."""
    test_dir = Path(__file__).parent / "without-values"
    cleanup_test_dir(test_dir)

    runner = CliRunner()

    result = runner.invoke(cli, ["render", "--workdir", str(test_dir), "--skip-output"])

    assert result.exit_code == 0, f"CLI failed with exit code {result.exit_code}\nOutput:\n{result.output}"

    # stdout should be empty (no YAML printed)
    assert "---" not in result.output, "Output should be empty when --skip-output is used"

    # .manifest.yaml should still be written
    manifest = test_dir / ".manifest.yaml"
    assert manifest.exists(), ".manifest.yaml should be written even with --skip-output"
    assert "---" in manifest.read_text(), ".manifest.yaml should contain YAML"

