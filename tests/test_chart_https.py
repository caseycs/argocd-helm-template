"""Tests for HTTPS chart download scenario."""

import sys
from pathlib import Path

# Add parent directory to path to import the main module
sys.path.insert(0, str(Path(__file__).parent.parent))

from argocd_helm_template import (
    load_application_yaml,
    extract_chart_info,
    download_chart,
)


def test_https_chart_download_flow(tmp_path):
    """Test complete HTTPS chart download flow.

    Tests the sequential flow:
    1. load_application_yaml
    2. extract_chart_info
    3. download_chart

    Verifies that the chart directory and files are created.
    """
    # Test directory paths
    test_dir = Path(__file__).parent / "chart-https"
    application_yaml = test_dir / "application.yaml"

    # Step 1: Load application.yaml
    app_yaml = load_application_yaml(application_yaml)
    assert app_yaml is not None
    assert app_yaml.get("kind") == "Application"

    # Step 2: Extract chart info
    repo_url, chart_name, version, is_git = extract_chart_info(app_yaml)
    assert repo_url == "https://argoproj.github.io/argo-helm"
    assert chart_name == "argo-cd"
    assert version == "7.9.1"
    assert is_git is False

    # Step 3: Download chart (using temp directory for .chart)
    chart_dir = tmp_path / ".chart"
    download_chart(repo_url, chart_name, version, chart_dir, is_git, verbose=True)

    # Verify chart directory was created
    assert chart_dir.exists(), f"Chart directory {chart_dir} was not created"

    # Verify chart subdirectory exists
    chart_path = chart_dir / chart_name
    assert chart_path.exists(), f"Chart subdirectory {chart_path} was not created"

    # Verify Chart.yaml exists
    chart_yaml = chart_path / "Chart.yaml"
    assert chart_yaml.exists(), f"Chart.yaml not found at {chart_yaml}"
