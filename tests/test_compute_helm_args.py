"""Tests for compute_helm_args function."""

import sys
from pathlib import Path
import pytest
import tempfile

# Add parent directory to path to import the main module
sys.path.insert(0, str(Path(__file__).parent.parent))

from argocd_helm_template import compute_helm_args
import click


def test_compute_helm_args_with_release_name_and_skip_crds():
    """Test compute_helm_args with release name and skipCrds enabled."""
    app_yaml = {
        "metadata": {
            "name": "karpenter-app"
        },
        "spec": {
            "sources": [
                {
                    "repoURL": "public.ecr.aws/karpenter",
                    "targetRevision": "1.5.2",
                    "chart": "karpenter",
                    "helm": {
                        "releaseName": "karpenter",
                        "skipCrds": True,
                        "valueFiles": []
                    }
                }
            ]
        }
    }

    workdir = Path.cwd()
    args = compute_helm_args(app_yaml, workdir)

    # Should contain release name and skipCrds flag
    assert "--release-name" in args
    assert "karpenter" in args
    assert "--skip-crds" in args


def test_compute_helm_args_no_helm_config():
    """Test compute_helm_args with no helm configuration."""
    app_yaml = {
        "metadata": {
            "name": "karpenter-app"
        },
        "spec": {
            "sources": [
                {
                    "repoURL": "public.ecr.aws/karpenter",
                    "targetRevision": "1.5.2",
                    "chart": "karpenter"
                }
            ]
        }
    }

    workdir = Path.cwd()
    args = compute_helm_args(app_yaml, workdir)

    # Should return empty list when no helm config
    assert args == ['--release-name', 'karpenter-app']


def test_compute_helm_args_with_no_release_name():
    """Test compute_helm_args without release name."""
    app_yaml = {
        "metadata": {
            "name": "karpenter-app"
        },
        "spec": {
            "sources": [
                {
                    "repoURL": "public.ecr.aws/karpenter",
                    "targetRevision": "1.5.2",
                    "chart": "karpenter",
                    "helm": {
                        "valueFiles": []
                    }
                }
            ]
        }
    }

    workdir = Path.cwd()
    args = compute_helm_args(app_yaml, workdir)

    assert args == ['--release-name', 'karpenter-app']


def test_compute_helm_args_with_single_values_file_without_reference():
    """Test compute_helm_args with a single values file."""
    workdir = Path.cwd()

    app_yaml = {
        "metadata": {
            "name": "karpenter-app"
        },
        "spec": {
            "sources": [
                {
                    "repoURL": "public.ecr.aws/karpenter",
                    "targetRevision": "1.5.2",
                    "chart": "karpenter",
                    "helm": {
                        "valueFiles": ["values.yaml"]
                    }
                },
                {
                    "repoURL": "https://github.com/org/values-repo",
                    "ref": "values"
                }
            ]
        }
    }

    with pytest.raises(click.ClickException) as exc_info:
        compute_helm_args(app_yaml, workdir)

    assert "should start with mapping" in str(exc_info.value)


def test_compute_helm_args_with_single_values_file():
    """Test compute_helm_args with a single values file."""
    # repoRoot is the parent directory of the current test file location
    repoRoot = Path(__file__).parent.parent
    workdir = Path.cwd()


    app_yaml = {
        "metadata": {
            "name": "karpenter-app"
        },
        "spec": {
            "sources": [
                {
                    "repoURL": "public.ecr.aws/karpenter",
                    "targetRevision": "1.5.2",
                    "chart": "karpenter",
                    "helm": {
                        "valueFiles": ["$values/dir/values.yaml"]
                    }
                },
                {
                    "repoURL": "https://github.com/org/values-repo",
                    "ref": "values"
                }
            ]
        }
    }

    args = compute_helm_args(app_yaml, workdir)
    assert args == ['--release-name', 'karpenter-app', '-f', f"{repoRoot}/dir/values.yaml"]


def test_compute_helm_args_with_multiple_values_files():
    """Test compute_helm_args with multiple values files."""
    # repoRoot is the parent directory of the current test file location
    repoRoot = Path(__file__).parent.parent
    workdir = Path.cwd()

    app_yaml = {
        "metadata": {
            "name": "karpenter-app"
        },
        "spec": {
            "sources": [
                {
                    "repoURL": "public.ecr.aws/karpenter",
                    "targetRevision": "1.5.2",
                    "chart": "karpenter",
                    "helm": {
                        "valueFiles": ["$values/values1.yaml", "$values/values2.yaml"]
                    }
                },
                {
                    "repoURL": "https://github.com/org/values-repo",
                    "ref": "values"
                }
            ]
        }
    }

    args = compute_helm_args(app_yaml, workdir)

    # Should contain release name, skipCrds, and two values files
    assert args == ['--release-name', 'karpenter-app', '-f', f"{repoRoot}/values1.yaml", "-f", f"{repoRoot}/values2.yaml"]


def test_compute_helm_args_with_ref_mapping_override():
    """Test compute_helm_args with ref mapping override."""
    workdir = Path.cwd()

    app_yaml = {
        "metadata": {
            "name": "karpenter-app"
        },
        "spec": {
            "sources": [
                {
                    "repoURL": "public.ecr.aws/karpenter",
                    "targetRevision": "1.5.2",
                    "chart": "karpenter",
                    "helm": {
                        "valueFiles": ["$values/values.yaml"]
                    }
                },
                {
                    "repoURL": "https://github.com/org/values-repo",
                    "ref": "values"
                }
            ]
        }
    }

    ref_map_override = {"values": "/tmp/"}
    args = compute_helm_args(app_yaml, workdir, ref_map_override)

    # Should contain release name and resolved values file
    assert args == ['--release-name', 'karpenter-app', "-f", "/tmp/values.yaml"]


def test_compute_helm_args_missing_ref_outside_of_git_repo_raises_error():
    """Test compute_helm_args raises error when ref is not mapped and workdir is not in git."""
    # Create a temporary directory that is NOT in a git repository
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)

        app_yaml = {
            "metadata": {
                "name": "karpenter-app"
            },
            "spec": {
                "sources": [
                    {
                        "repoURL": "public.ecr.aws/karpenter",
                        "targetRevision": "1.5.2",
                        "chart": "karpenter",
                        "helm": {
                            "valueFiles": ["$values/values.yaml"]
                        }
                    },
                    {
                        "repoURL": "https://github.com/org/values-repo",
                        "ref": "values"
                    }
                ]
            }
        }

        # No ref mapping provided, and workdir is not in git repo
        # This should raise ClickException
        with pytest.raises(click.ClickException) as exc_info:
            compute_helm_args(app_yaml, workdir)

        assert "git repository" in str(exc_info.value)

def test_compute_helm_args_mapping():
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)

        app_yaml = {
            "metadata": {
                "name": "karpenter-app"
            },
            "spec": {
                "sources": [
                    {
                        "repoURL": "public.ecr.aws/karpenter",
                        "targetRevision": "1.5.2",
                        "chart": "karpenter",
                        "helm": {
                            "valueFiles": ["$vals/dir/values.yaml"]
                        }
                    },
                    {
                        "repoURL": "https://github.com/org/values-repo",
                        "ref": "vals"
                    }
                ]
            }
        }

        args = compute_helm_args(app_yaml, workdir, ref_map_override = {"vals": "/tmp/values-repo"}, verbose=True)
        assert args == ['--release-name', 'karpenter-app', '-f', "/tmp/values-repo/dir/values.yaml"]


def test_compute_helm_args_missing_mapping():
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)

        app_yaml = {
            "metadata": {
                "name": "karpenter-app"
            },
            "spec": {
                "sources": [
                    {
                        "repoURL": "public.ecr.aws/karpenter",
                        "targetRevision": "1.5.2",
                        "chart": "karpenter",
                        "helm": {
                            "valueFiles": ["$vals1/dir/values.yaml"]
                        }
                    },
                    {
                        "repoURL": "https://github.com/org/values-repo",
                        "ref": "vals1"
                    }
                ]
            }
        }

        # mapping for vals1 not defined, should fail
        with pytest.raises(click.ClickException) as exc_info:
            compute_helm_args(app_yaml, workdir, ref_map_override = {"vals2": "/tmp/values-repo"})

        assert "Ref 'vals1' in valueFile '$vals1/dir/values.yaml' not found in mapping" in str(exc_info.value)



def test_compute_helm_args_unmapped_ref_in_values_file_raises_error():
    """Test compute_helm_args raises error when valueFile references unmapped ref."""
    workdir = Path.cwd()

    app_yaml = {
        "metadata": {
            "name": "karpenter-app"
        },
        "spec": {
            "sources": [
                {
                    "repoURL": "public.ecr.aws/karpenter",
                    "targetRevision": "1.5.2",
                    "chart": "karpenter",
                    "helm": {
                        "valueFiles": ["$nonexistent/values.yaml"]
                    }
                },
                {
                    "repoURL": "https://github.com/org/values-repo",
                    "ref": "values"
                }
            ]
        }
    }

    # valueFile references 'nonexistent' ref which is not in sources mapping
    # This should raise ClickException
    with pytest.raises(click.ClickException) as exc_info:
        compute_helm_args(app_yaml, workdir)

    assert "Ref 'nonexistent' in valueFile '$nonexistent/values.yaml' not found in mapping" in str(exc_info.value)


def test_compute_helm_args_multiple_refs_without_mapping_raises_error():
    """Test compute_helm_args raises error with multiple refs and no mapping."""
    workdir = Path.cwd()

    app_yaml = {
        "metadata": {
            "name": "karpenter-app"
        },
        "spec": {
            "sources": [
                {
                    "repoURL": "public.ecr.aws/karpenter",
                    "targetRevision": "1.5.2",
                    "chart": "karpenter",
                    "helm": {
                        "valueFiles": []
                    }
                },
                {
                    "repoURL": "https://github.com/org/values-repo",
                    "ref": "values"
                },
                {
                    "repoURL": "https://github.com/org/other-repo",
                    "ref": "other"
                }
            ]
        }
    }

    # Multiple ref sources without mapping should raise error
    with pytest.raises(click.ClickException) as exc_info:
        compute_helm_args(app_yaml, workdir)

    assert "Multiple ref sources" in str(exc_info.value)
