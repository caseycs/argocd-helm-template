"""Test utilities for cleanup and common operations."""

import shutil
from pathlib import Path


def cleanup_test_dir(test_dir: Path):
    """Clean up chart cache and manifest files before test.

    Removes:
    - .chart directory (Helm registry cache)
    - .chart_repo directory (Git chart cache)
    - .manifest.yaml (rendered manifests)
    - .manifest.secrets.yaml (decoded secrets)

    Args:
        test_dir: Test directory to clean
    """
    # Remove .chart directory
    chart_dir = test_dir / ".chart"
    if chart_dir.exists():
        shutil.rmtree(chart_dir)

    # Remove .chart_repo directory (for git charts)
    chart_repo_dir = test_dir / ".chart_repo"
    if chart_repo_dir.exists():
        shutil.rmtree(chart_repo_dir)

    # Remove manifest files
    for manifest_file in [".manifest.yaml", ".manifest.secrets.yaml"]:
        manifest = test_dir / manifest_file
        if manifest.exists():
            manifest.unlink()
