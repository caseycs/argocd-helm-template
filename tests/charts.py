"""End-to-end tests for CLI chart rendering using Click framework."""

import sys
from pathlib import Path

# Add parent directory to path to import the main module
sys.path.insert(0, str(Path(__file__).parent.parent))

from click.testing import CliRunner

from argocd_helm_template import cli


def test_oci_chart_render_e2e():
    """End-to-end test: Render OCI chart via Click CLI.

    Tests the complete workflow:
    1. Invokes 'render' command with OCI chart test data
    2. Verifies CLI exit code is 0
    3. Verifies YAML output is present
    4. Verifies Chart.yaml is downloaded

    Note: Cache directories are cleaned up automatically by conftest.py pre-hook.

    Tests against: public.ecr.aws/karpenter karpenter:1.5.2
    """
    runner = CliRunner()
    test_dir = Path(__file__).parent / "chart-oci"
    chart_dir = test_dir / ".chart"

    # Invoke the render command via Click CLI
    result = runner.invoke(cli, ["render", "--workdir", str(test_dir)])

    # Verify CLI executed successfully (exit code 0)
    assert result.exit_code == 0, f"CLI failed with exit code {result.exit_code}\nOutput:\n{result.output}"

    # Verify YAML output
    assert "---" in result.output, "Output does not contain YAML"

    # Verify Chart.yaml was downloaded
    chart_yaml = chart_dir / "karpenter" / "Chart.yaml"
    assert chart_yaml.exists(), f"Chart.yaml not found at {chart_yaml}"


def test_https_chart_render_e2e():
    """End-to-end test: Render HTTPS Helm repository chart via Click CLI.

    Tests the complete workflow for HTTPS Helm repositories:
    1. Invokes 'render' command with HTTPS chart test data
    2. Verifies CLI exit code is 0
    3. Verifies YAML output is present
    4. Verifies Chart.yaml is downloaded

    Note: Cache directories are cleaned up automatically by conftest.py pre-hook.

    Tests against: https://argoproj.github.io/argo-helm argo-cd:7.9.1
    """
    runner = CliRunner()
    test_dir = Path(__file__).parent / "chart-https"
    chart_dir = test_dir / ".chart"

    # Invoke the render command via Click CLI
    result = runner.invoke(cli, ["render", "--workdir", str(test_dir)])

    # Verify CLI executed successfully (exit code 0)
    assert result.exit_code == 0, f"CLI failed with exit code {result.exit_code}\nOutput:\n{result.output}"

    # Verify YAML output
    assert "---" in result.output, "Output does not contain YAML"

    # Verify Chart.yaml was downloaded
    chart_yaml = chart_dir / "argo-cd" / "Chart.yaml"
    assert chart_yaml.exists(), f"Chart.yaml not found at {chart_yaml}"


def test_git_chart_render_e2e():
    """End-to-end test: Render Git-based chart via Click CLI.

    Tests the complete workflow for Git repository charts:
    1. Invokes 'render' command with Git chart test data
    2. Verifies CLI exit code is 0
    3. Verifies YAML output is present
    4. Verifies Chart.yaml is cloned from git in .chart_repo
    5. Verifies symlink is created in .chart directory

    Note: Cache directories are cleaned up automatically by conftest.py pre-hook.

    Tests against: https://github.com/argoproj/argo-helm charts/argo-events:argo-events-2.4.19
    """
    runner = CliRunner()
    test_dir = Path(__file__).parent / "chart-git"
    chart_repo_dir = test_dir / ".chart_repo"
    chart_dir = test_dir / ".chart"

    # Invoke the render command via Click CLI
    result = runner.invoke(cli, ["render", "--workdir", str(test_dir)])

    # Verify CLI executed successfully (exit code 0)
    assert result.exit_code == 0, f"CLI failed with exit code {result.exit_code}\nOutput:\n{result.output}"

    # Verify YAML output
    assert "---" in result.output, "Output does not contain YAML"

    # Verify Chart.yaml exists in the git repo cache (.chart_repo)
    # Git charts are cached in .chart_repo/{repo-name}/path
    chart_yaml_in_repo = chart_repo_dir / "github.com-argoproj-argo-helm" / "charts" / "argo-events" / "Chart.yaml"
    assert chart_yaml_in_repo.exists(), f"Chart.yaml not found in git cache at {chart_yaml_in_repo}"

    # Verify symlink is created in .chart directory pointing to the git repo chart
    chart_symlink = chart_dir / "argo-events"
    assert chart_symlink.exists(), f"Chart symlink not found at {chart_symlink}"
    assert chart_symlink.is_symlink(), f"Expected {chart_symlink} to be a symlink"
