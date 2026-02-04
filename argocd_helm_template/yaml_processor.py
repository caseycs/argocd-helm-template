"""YAML post-processing utilities."""

import base64
import yaml

from .utils import log


class YamlPostProcessor:
    """Post-processes YAML output, including decoding base64 secrets."""

    class _LiteralString(str):
        """String subclass to mark strings that should use literal block scalar style."""
        pass

    def __init__(self, yaml_output: str):
        """
        Initialize with raw YAML output.

        Args:
            yaml_output: Raw YAML output string (possibly multi-document)
        """
        self._yaml_output = yaml_output

    @staticmethod
    def _represent_literal_str(dumper, data):
        """Custom YAML representer for LiteralString to use literal block scalar style."""
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')

    @staticmethod
    def _represent_str(dumper, data):
        """Custom YAML representer for regular strings to preserve multiline formatting."""
        if '\n' in data:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)

    def _create_dumper(self):
        """Create a custom YAML dumper with our representers."""
        class CustomDumper(yaml.SafeDumper):
            pass

        CustomDumper.add_representer(self._LiteralString, self._represent_literal_str)
        CustomDumper.add_representer(str, self._represent_str)
        return CustomDumper

    def _decode_secret(self, doc: dict) -> dict:
        """Decode base64 values in a Secret document."""
        log(f"Processing Secret: {doc.get('metadata', {}).get('name', 'unknown')}")

        if 'data' in doc and isinstance(doc['data'], dict):
            for key, value in doc['data'].items():
                if isinstance(value, str):
                    try:
                        decoded = base64.b64decode(value).decode('utf-8')
                        doc['data'][key] = self._LiteralString(decoded)
                        log(f"  Decoded key: {key}")
                    except Exception as e:
                        log(f"  Failed to decode key {key}: {e}")
        return doc

    def decode_secrets(self) -> str:
        """
        Decode base64 values in Secret resources.

        Returns:
            Processed YAML output with decoded Secret values
        """
        documents = []
        try:
            for doc in yaml.safe_load_all(self._yaml_output):
                if doc is None:
                    continue

                if isinstance(doc, dict) and doc.get('kind') == 'Secret':
                    doc = self._decode_secret(doc)

                documents.append(doc)
        except yaml.YAMLError as e:
            log(f"Warning: Failed to parse YAML: {e}")
            return self._yaml_output

        # Convert documents back to YAML
        dumper = self._create_dumper()
        result_parts = []
        for doc in documents:
            result_parts.append(yaml.dump(
                doc,
                Dumper=dumper,
                default_flow_style=False,
                sort_keys=False,
                width=float("inf"),
                allow_unicode=True
            ))

        return '---\n' + '\n---\n'.join(result_parts)
