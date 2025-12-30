"""Tests for compute_helm_args function."""

import sys
from pathlib import Path
import pytest
import tempfile
import yaml

# Add parent directory to path to import the main module
sys.path.insert(0, str(Path(__file__).parent.parent))

from argocd_helm_template import compute_helm_args
from argocd_application import ArgocdApplication
import click


class InvalidApplicationYAML(Exception):
    """Raised when application YAML structure is invalid."""
    pass


class ApplicationValidationError(Exception):
    """Raised when application configuration validation fails."""
    pass


def compute_helm_args_with_validation(yaml_string: str, workdir: Path, ref_map_override: dict = None, verbose: bool = False) -> list[str]:
    """
    Test wrapper that validates ArgocdApplication and computes helm arguments.

    This wrapper:
    1. Parses YAML string into dictionary
    2. Creates ArgocdApplication from yaml_dict
    3. Validates the application
    4. Throws ClickException if invalid
    5. Calls compute_helm_args() with validated application

    Args:
        yaml_string: Raw YAML string content
        workdir: Working directory
        ref_map_override: Optional mapping of ref names to local paths
        verbose: Enable verbose logging

    Returns:
        list[str]: Command-line arguments for helm template command.

    Raises:
        InvalidApplicationYAML: If application YAML structure is invalid
        ApplicationValidationError: If application configuration validation fails
    """
    # Parse YAML string
    yaml_dict = yaml.safe_load(yaml_string)

    # Create ArgocdApplication
    try:
        app = ArgocdApplication(yaml_dict)
    except ValueError as e:
        raise InvalidApplicationYAML(str(e))

    # Validate application (throws on first error)
    try:
        app.validate()
    except ValueError as e:
        raise ApplicationValidationError(str(e))

    # Call compute_helm_args with validated application
    try:
        return compute_helm_args(app, workdir, ref_map_override, verbose)
    except click.ClickException as e:
        raise ApplicationValidationError(str(e))


def test_compute_helm_args_with_release_name_and_skip_crds():
    """Test compute_helm_args with release name and skipCrds enabled."""
    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
      helm:
        releaseName: karpenter
        skipCrds: true
        valueFiles: []
"""

    workdir = Path.cwd()
    args = compute_helm_args_with_validation(app_yaml, workdir)

    assert args == ['--release-name', 'karpenter', '--skip-crds'], \
        "Should return custom release name and skip crds flag"



def test_compute_helm_args_no_helm_config():
    """Test compute_helm_args with no helm configuration."""
    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
"""

    workdir = Path.cwd()
    args = compute_helm_args_with_validation(app_yaml, workdir)

    assert args == ['--release-name', 'karpenter-app'], \
        "Should return only release name (from argocd app name), no skip crds"


def test_compute_helm_args_with_single_values_file_without_reference():
    """Test compute_helm_args with a single values file."""
    workdir = Path.cwd()

    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
      helm:
        valueFiles:
          - values.yaml
    - repoURL: https://github.com/org/values-repo
      ref: values
"""

    with pytest.raises(ApplicationValidationError) as exc_info:
        compute_helm_args_with_validation(app_yaml, workdir)

    assert "must use ref prefix" in str(exc_info.value), \
        "Each helm value file path should start with mapping reference ($val)"


def test_compute_helm_args_with_single_values_file():
    """Test compute_helm_args with a single values file."""
    # repoRoot is the parent directory of the current test file location
    repoRoot = Path(__file__).parent.parent
    workdir = Path.cwd()

    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
      helm:
        valueFiles:
          - $values/dir/values.yaml
    - repoURL: https://github.com/org/values-repo
      ref: values
"""

    args = compute_helm_args_with_validation(app_yaml, workdir)
    assert args == ['--release-name', 'karpenter-app', '-f', f"{repoRoot}/dir/values.yaml"], \
        "First reference ($values) should be be mapped to workdir repo root"


def test_compute_helm_args_with_multiple_values_files():
    """Test compute_helm_args with multiple values files."""
    # repoRoot is the parent directory of the current test file location
    repoRoot = Path(__file__).parent.parent
    workdir = Path.cwd()

    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
      helm:
        valueFiles:
          - $values/values1.yaml
          - $values/values2.yaml
    - repoURL: https://github.com/org/values-repo
      ref: values
"""

    args = compute_helm_args_with_validation(app_yaml, workdir)

    # Should contain release name, skipCrds, and two values files
    assert args == ['--release-name', 'karpenter-app', '-f', f"{repoRoot}/values1.yaml", "-f", f"{repoRoot}/values2.yaml"], \
        "Both values files reference ($values) should be be mapped to workdir repo root"


def test_compute_helm_args_with_ref_mapping_override():
    """Test compute_helm_args with ref mapping override."""
    workdir = Path.cwd()

    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
      helm:
        valueFiles:
          - $values/dir/values1.yaml
          - $values/dir/values2.yaml
    - repoURL: https://github.com/org/values-repo
      ref: values
"""

    ref_map_override = {"values": "/tmp/"}
    args = compute_helm_args_with_validation(app_yaml, workdir, ref_map_override)

    assert args == ['--release-name', 'karpenter-app', "-f", "/tmp/dir/values1.yaml", "-f", "/tmp/dir/values2.yaml"], \
        "Custom mapping override ($values->/tmp/) should work"


def test_compute_helm_args_missing_ref_outside_of_git_repo_raises_error():
    """Test compute_helm_args raises error when ref is not mapped and workdir is not in git."""
    # Create a temporary directory that is NOT in a git repository
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)

        app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
      helm:
        valueFiles:
          - $values/values.yaml
    - repoURL: https://github.com/org/values-repo
      ref: values
"""

        # No ref mapping provided, and workdir is not in git repo
        # This should raise ApplicationValidationError
        with pytest.raises(ApplicationValidationError) as exc_info:
            compute_helm_args_with_validation(app_yaml, workdir)

        assert "git repository" in str(exc_info.value), \
            "Default mapping should not work when workdir is not part of git repository"

def test_compute_helm_args_missing_mapping():
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)

        app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
      helm:
        valueFiles:
          - $vals1/dir/values.yaml
    - repoURL: https://github.com/org/values-repo
      ref: vals1
"""

        # mapping for vals1 not defined, should fail
        with pytest.raises(ApplicationValidationError) as exc_info:
            compute_helm_args_with_validation(app_yaml, workdir, ref_map_override = {"vals2": "/tmp/values-repo"})

        assert "Ref 'vals1' in valueFile '$vals1/dir/values.yaml' not found in mapping" in str(exc_info.value), \
            "Failure expected when provided mapping (vals2) does not match required ones (vals1)"


def test_compute_helm_args_unmapped_ref_in_values_file_raises_error():
    workdir = Path.cwd()

    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
      helm:
        valueFiles:
          - $nonexistent/values.yaml
    - repoURL: https://github.com/org/values-repo
      ref: values
"""

    # This should raise ApplicationValidationError
    with pytest.raises(ApplicationValidationError) as exc_info:
        compute_helm_args_with_validation(app_yaml, workdir)

    assert "valueFile '$nonexistent/values.yaml' references undefined ref 'nonexistent'" in str(exc_info.value), \
        "Should fail when valueFiles mapping ($nonexistent) use unknown references (only ref: values defined)"


def test_compute_helm_args_multiple_refs_without_mapping_raises_error():
    """Test compute_helm_args raises error with multiple refs and no mapping."""
    workdir = Path.cwd()

    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
      helm:
        valueFiles: []
    - repoURL: https://github.com/org/values-repo
      ref: values
    - repoURL: https://github.com/org/other-repo
      ref: other
"""

    # Multiple ref sources without mapping should raise error
    with pytest.raises(ApplicationValidationError) as exc_info:
        compute_helm_args_with_validation(app_yaml, workdir)

    assert "Multiple ref sources" in str(exc_info.value), \
        "Should fail when defined references (values, other) are unused by values files"


def test_compute_helm_args_duplicate_refs():
    """Test compute_helm_args raises error with multiple refs and no mapping."""
    workdir = Path.cwd()

    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
      helm:
        valueFiles: []
    - repoURL: https://github.com/org/values-repo
      ref: values
    - repoURL: https://github.com/org/other-repo
      ref: values
"""

    # Multiple ref sources without mapping should raise error
    with pytest.raises(ApplicationValidationError) as exc_info:
        compute_helm_args_with_validation(app_yaml, workdir)

    assert "Duplicate ref sources" in str(exc_info.value), \
        "Should fail when sources have duplicate refs"


def test_compute_helm_args_multiple_charts():
    workdir = Path.cwd()

    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
      helm:
        valueFiles: []
    - repoURL: public.ecr.aws/woodworker
      targetRevision: 1.5.2
      chart: woodworker
      helm:
        valueFiles: []
"""

    with pytest.raises(ApplicationValidationError) as exc_info:
        compute_helm_args_with_validation(app_yaml, workdir)

    assert "Only one Helm chart per application is supported" in str(exc_info.value), \
        "Should fail when application has multiple helm charts"
    

def test_compute_helm_args_incomplete_charts():
    workdir = Path.cwd()

    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
    - repoURL: public.ecr.aws/woodworker
      targetRevision: 1.5.2
      helm:
        valueFiles: []
"""

    with pytest.raises(ApplicationValidationError) as exc_info:
        compute_helm_args_with_validation(app_yaml, workdir)

    assert "Source" in str(exc_info.value) and "invalid" in str(exc_info.value), \
        "Should fail when application source has unexpected format"


def test_compute_helm_args_no_application():
    """Test compute_helm_args raises error with multiple refs and no mapping."""
    workdir = Path.cwd()

    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: SomeKind
metadata:
  name: karpenter-app
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      targetRevision: 1.5.2
      chart: karpenter
      helm:
        valueFiles: []
"""

    # Multiple ref sources without mapping should raise error
    with pytest.raises(ApplicationValidationError) as exc_info:
        compute_helm_args_with_validation(app_yaml, workdir)

    assert "Invalid resource kind: 'Application' expected" in str(exc_info.value), \
        "Should fail when non-application k8s resource is present"
    
def test_compute_helm_args_no_helm():
    workdir = Path.cwd()

    app_yaml = """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: kustomize-example
spec:
  project: default
  source:
    path: examples/helloWorld
    repoURL: 'https://github.com/kubernetes-sigs/kustomize'
    targetRevision: HEAD
  destination:
    namespace: default
    server: 'https://kubernetes.default.svc'
"""

    # Multiple ref sources without mapping should raise error
    with pytest.raises(ApplicationValidationError) as exc_info:
        compute_helm_args_with_validation(app_yaml, workdir)

    assert "Source is invalid" in str(exc_info.value), \
        "Should fail for application without helm chart"
    