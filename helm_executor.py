"""Helm command execution and manifest processing utilities."""

import base64
import subprocess
from pathlib import Path
import yaml
from utils import log


class LiteralString(str):
    """String subclass to mark strings that should use literal block scalar style."""
    pass


def represent_literal_str(dumper, data):
    """Custom YAML representer for LiteralString to use literal block scalar style."""
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')


def represent_str(dumper, data):
    """Custom YAML representer for regular strings to preserve multiline formatting."""
    if '\n' in data:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


def process_secrets(yaml_output: str, secrets: bool = False, verbose: bool = False) -> str:
    """
    Post-process helm template output to decode base64 values in Secrets.

    Args:
        yaml_output: Raw YAML output from helm template
        secrets: Whether to decode base64 values in Secrets
        verbose: Enable verbose logging

    Returns:
        Processed YAML output with decoded Secret values (if secrets=True)
    """
    # If not decoding secrets, return original output
    if not secrets:
        return yaml_output

    # Load all YAML documents using native yaml.safe_load_all
    documents = []
    try:
        for doc in yaml.safe_load_all(yaml_output):
            if doc is None:
                continue

            # Process Secrets
            if isinstance(doc, dict) and doc.get('kind') == 'Secret':
                log(f"Processing Secret: {doc.get('metadata', {}).get('name', 'unknown')}", verbose)

                # Decode data section
                if 'data' in doc and isinstance(doc['data'], dict):
                    for key, value in doc['data'].items():
                        if isinstance(value, str):
                            try:
                                decoded = base64.b64decode(value).decode('utf-8')
                                # Wrap in LiteralString to force literal block scalar style
                                doc['data'][key] = LiteralString(decoded)
                                log(f"  Decoded key: {key}", verbose)
                            except Exception as e:
                                log(f"  Failed to decode key {key}: {e}", verbose)
                                # Keep original value if decoding fails
                                pass

            documents.append(doc)
    except yaml.YAMLError as e:
        log(f"Warning: Failed to parse YAML: {e}", verbose)
        return yaml_output  # Return original if parsing fails

    # Create custom dumper with our representers
    class CustomDumper(yaml.SafeDumper):
        pass

    CustomDumper.add_representer(LiteralString, represent_literal_str)
    CustomDumper.add_representer(str, represent_str)

    # Convert documents back to YAML
    result_parts = []
    for doc in documents:
        result_parts.append(yaml.dump(
            doc,
            Dumper=CustomDumper,
            default_flow_style=False,
            sort_keys=False,
            width=float("inf"),
            allow_unicode=True
        ))

    return '---\n' + '\n---\n'.join(result_parts)


def run_helm_template(chart_path: Path, helm_args: list[str], output_dir: Path = Path("."), secrets: bool = False, verbose: bool = False, print_output: bool = True):
    """
    Run helm template command with computed helm arguments and optionally post-process Secrets.

    Args:
        chart_path: Path to helm chart
        helm_args: Helm arguments from compute_helm_args (release name, values files, skipCrds, etc)
        output_dir: Directory to write manifests
        secrets: Whether to decode base64 in Secrets
        verbose: Enable verbose logging
        print_output: Whether to print output to stdout
    """
    # Build the helm template command
    # Syntax: helm template [NAME] [CHART] [flags]
    # NAME is optional (release name), CHART is the chart path
    cmd = ["helm", "template"]

    # Add helm arguments from compute_helm_args (includes release name, values files, skipCrds, etc)
    cmd.extend(helm_args)

    # Add chart path
    cmd.append(str(chart_path))

    log(f"Running: {' '.join(cmd)}", verbose)

    # Run helm template and capture output
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    stdout_output, stderr_output = process.communicate()

    if process.returncode != 0:
        raise RuntimeError(f"Helm template execution failed with exit code {process.returncode}:\n{stderr_output}")
    elif verbose and stderr_output:
        log(stderr_output, verbose)

    # Post-process to decode Secret values if requested
    if secrets:
        log("Post-processing Secrets to decode base64 values...", verbose)
    processed_output = process_secrets(stdout_output, secrets, verbose)

    # Determine output filename based on secrets flag
    manifest_filename = ".manifest.secrets.yaml" if secrets else ".manifest.yaml"
    manifest_path = output_dir / manifest_filename

    # Write processed output to manifest file
    with open(manifest_path, "w") as manifest_file:
        manifest_file.write(processed_output)

    # Print to stdout only if print_output is True
    if print_output:
        print(processed_output, end="")
