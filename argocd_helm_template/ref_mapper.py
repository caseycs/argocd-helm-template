"""Reference mapping utilities."""

from pathlib import Path
from .utils import log
from .git_helper import resolve_git_root


def build_ref_mapping(ref_sources: dict, workdir: Path, ref_map_override: dict = None, verbose: bool = False) -> dict:
    """
    Build a mapping from ref names to local paths.

    Priority:
    1. If ref_map_override is provided, use those mappings
    2. For the first ref source, use git root
    3. If there are more ref sources and no mapping provided, fail with error

    Returns:
        dict: Mapping of ref names to local paths (e.g., {"values": Path("/git/root")})

    Raises:
        RuntimeError: If multiple ref sources exist without mapping
    """
    if not ref_sources:
        return {}

    ref_mapping = {}

    if ref_map_override:
        # Parse and apply override mappings
        for ref_name, local_path in ref_map_override.items():
            ref_mapping[ref_name] = Path(local_path)
            log(f"Ref mapping override: {ref_name} -> {local_path}", verbose)
    else:
        # For the first ref source, use git root
        first_ref_name = next(iter(ref_sources.keys()))
        if len(ref_sources) > 1:
            raise RuntimeError(
                f"Error: Multiple ref sources found ({', '.join(ref_sources.keys())}) but no --ref-map provided. "
                "Please specify --ref-map to map each ref to a local path (e.g., --ref-map values=/path/to/values --ref-map other=/path/to/other)"
            )

        git_root = resolve_git_root(workdir, verbose)
        ref_mapping[first_ref_name] = git_root
        log(f"Ref mapping: {first_ref_name} -> {git_root}", verbose)

    return ref_mapping


def apply_ref_mapping_to_value_files(value_files: list[str], ref_mapping: dict, verbose: bool = False) -> list[Path]:
    """
    Apply ref mapping to valueFiles, replacing $ref_name/ prefixes with mapped paths.

    Args:
        value_files: List of value file paths (may contain $ref_name/ prefixes)
        ref_mapping: Mapping of ref names to local paths
        verbose: Enable verbose logging

    Returns:
        list[Path]: List of resolved value file paths
    """
    resolved_files = []

    for vf in value_files:
        # Check if value file starts with $ref_name/
        if vf.startswith("$"):
            # Extract ref name and path
            parts = vf[1:].split("/", 1)
            if len(parts) == 2:
                ref_name, relative_path = parts
                if ref_name in ref_mapping:
                    resolved_path = ref_mapping[ref_name] / relative_path
                    log(f"Mapped valueFile: {vf} -> {resolved_path}", verbose)
                    resolved_files.append(resolved_path)
                else:
                    raise RuntimeError(f"Error: Ref '{ref_name}' in valueFile '{vf}' not found in mapping")
            else:
                raise RuntimeError(f"Error: valueFile '{vf}', ref/path expected but not found")
        else:
            raise RuntimeError(f"Error: valueFile '{vf}', should start with mapping")

    return resolved_files


