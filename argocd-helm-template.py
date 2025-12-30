#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pyyaml",
#   "click>=8.0",
# ]
# ///
"""
ArgoCD Helm Template - Render Helm charts from ArgoCD applications.
Supports rendering Kubernetes manifests from ArgoCD application definitions.
"""

from argocd_helm_template import cli

if __name__ == "__main__":
    cli()
