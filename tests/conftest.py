"""Global pytest configuration and fixtures for all tests."""

import shutil
from pathlib import Path
import pytest


@pytest.fixture(scope="function", autouse=True)
def cleanup_chart_cache():
    """Global pre-hook: Clean up chart cache directories before each test.

    This fixture automatically runs before every test function and cleans up:
    - .chart directory (used for OCI and HTTPS charts)
    - .chart_repo directory (used for Git-based charts)
    - .manifest.yaml and .manifest.secrets.yaml files

    Ensures clean state for chart downloads/clones.
    """
    test_dirs = [
        Path(__file__).parent / "chart-oci",
        Path(__file__).parent / "chart-https",
        Path(__file__).parent / "chart-git",
    ]

    # Clean up before test
    for test_dir in test_dirs:
        # Remove .chart directory
        chart_dir = test_dir / ".chart"
        if chart_dir.exists():
            shutil.rmtree(chart_dir)

        # Remove .chart_repo directory (for git charts)
        chart_repo_dir = test_dir / ".chart_repo"
        if chart_repo_dir.exists():
            shutil.rmtree(chart_repo_dir)

        # Remove manifest files
        manifest_file = test_dir / ".manifest.yaml"
        if manifest_file.exists():
            manifest_file.unlink()

        secrets_manifest = test_dir / ".manifest.secrets.yaml"
        if secrets_manifest.exists():
            secrets_manifest.unlink()

    # Run test
    yield

    # Optional: Clean up after test (commented out to preserve test artifacts for inspection)
    # Uncomment if you prefer a completely clean state after each test
    # for test_dir in test_dirs:
    #     chart_dir = test_dir / ".chart"
    #     if chart_dir.exists():
    #         shutil.rmtree(chart_dir)
    #     chart_repo_dir = test_dir / ".chart_repo"
    #     if chart_repo_dir.exists():
    #         shutil.rmtree(chart_repo_dir)
