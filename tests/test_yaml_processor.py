"""Tests for YamlPostProcessor class."""

import sys
from pathlib import Path
import base64
import pytest
import yaml

# Add parent directory to path to import the main module
sys.path.insert(0, str(Path(__file__).parent.parent))

from argocd_helm_template.yaml_processor import YamlPostProcessor


class TestYamlPostProcessorDecodeSecrets:
    """Tests for decode_secrets method."""

    def test_decode_single_secret(self):
        """Test decoding a single Secret with base64 data."""
        secret_yaml = """
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
data:
  username: YWRtaW4=
  password: cGFzc3dvcmQxMjM=
"""
        processor = YamlPostProcessor(secret_yaml)
        result = processor.decode_secrets()

        # Parse result to verify decoded values
        docs = list(yaml.safe_load_all(result))
        assert len(docs) == 1

        secret = docs[0]
        assert secret['kind'] == 'Secret'
        assert secret['data']['username'] == 'admin'
        assert secret['data']['password'] == 'password123'

    def test_decode_multiline_secret_value(self):
        """Test decoding a Secret with multiline base64 data."""
        multiline_content = "line1\nline2\nline3"
        encoded = base64.b64encode(multiline_content.encode()).decode()

        secret_yaml = f"""
apiVersion: v1
kind: Secret
metadata:
  name: multiline-secret
data:
  config: {encoded}
"""
        processor = YamlPostProcessor(secret_yaml)
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        assert docs[0]['data']['config'] == multiline_content

    def test_preserves_non_secret_resources(self):
        """Test that non-Secret resources are preserved unchanged."""
        configmap_yaml = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
data:
  key: value
"""
        processor = YamlPostProcessor(configmap_yaml)
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        assert len(docs) == 1
        assert docs[0]['kind'] == 'ConfigMap'
        assert docs[0]['data']['key'] == 'value'

    def test_multi_document_yaml_with_mixed_resources(self):
        """Test processing multi-document YAML with Secrets and other resources."""
        multi_doc_yaml = """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
data:
  key: value
---
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
data:
  token: c2VjcmV0LXRva2Vu
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-deployment
spec:
  replicas: 1
"""
        processor = YamlPostProcessor(multi_doc_yaml)
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        assert len(docs) == 3

        # ConfigMap unchanged
        assert docs[0]['kind'] == 'ConfigMap'

        # Secret decoded
        assert docs[1]['kind'] == 'Secret'
        assert docs[1]['data']['token'] == 'secret-token'

        # Deployment unchanged
        assert docs[2]['kind'] == 'Deployment'

    def test_invalid_base64_data_preserved(self):
        """Test that invalid base64 data is preserved as-is."""
        secret_yaml = """
apiVersion: v1
kind: Secret
metadata:
  name: bad-secret
data:
  valid: YWRtaW4=
  invalid: not-valid-base64!!!
"""
        processor = YamlPostProcessor(secret_yaml)
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        secret = docs[0]

        # Valid base64 should be decoded
        assert secret['data']['valid'] == 'admin'
        # Invalid base64 should be preserved
        assert secret['data']['invalid'] == 'not-valid-base64!!!'

    def test_empty_yaml(self):
        """Test processing empty YAML."""
        processor = YamlPostProcessor("")
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        # Filter out None documents
        docs = [d for d in docs if d is not None]
        assert len(docs) == 0

    def test_secret_without_data_field(self):
        """Test processing Secret without data field."""
        secret_yaml = """
apiVersion: v1
kind: Secret
metadata:
  name: empty-secret
type: Opaque
"""
        processor = YamlPostProcessor(secret_yaml)
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        assert len(docs) == 1
        assert docs[0]['kind'] == 'Secret'
        assert 'data' not in docs[0]

    def test_secret_with_null_data(self):
        """Test processing Secret with null data field."""
        secret_yaml = """
apiVersion: v1
kind: Secret
metadata:
  name: null-data-secret
data: null
"""
        processor = YamlPostProcessor(secret_yaml)
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        assert len(docs) == 1
        assert docs[0]['data'] is None

    def test_secret_with_non_string_values(self):
        """Test processing Secret with non-string data values."""
        secret_yaml = """
apiVersion: v1
kind: Secret
metadata:
  name: mixed-secret
data:
  string_value: YWRtaW4=
  int_value: 123
  bool_value: true
"""
        processor = YamlPostProcessor(secret_yaml)
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        secret = docs[0]

        # String value should be decoded
        assert secret['data']['string_value'] == 'admin'
        # Non-string values preserved
        assert secret['data']['int_value'] == 123
        assert secret['data']['bool_value'] is True

    def test_invalid_yaml_returns_original(self):
        """Test that invalid YAML returns original content."""
        invalid_yaml = "{{{{ invalid yaml content"
        processor = YamlPostProcessor(invalid_yaml)
        result = processor.decode_secrets()

        assert result == invalid_yaml

    def test_multiple_secrets(self):
        """Test processing multiple Secrets in one document."""
        multi_secret_yaml = """---
apiVersion: v1
kind: Secret
metadata:
  name: secret-one
data:
  key1: dmFsdWUx
---
apiVersion: v1
kind: Secret
metadata:
  name: secret-two
data:
  key2: dmFsdWUy
"""
        processor = YamlPostProcessor(multi_secret_yaml)
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        assert len(docs) == 2

        assert docs[0]['metadata']['name'] == 'secret-one'
        assert docs[0]['data']['key1'] == 'value1'

        assert docs[1]['metadata']['name'] == 'secret-two'
        assert docs[1]['data']['key2'] == 'value2'

    def test_null_documents_filtered(self):
        """Test that null documents (from empty YAML separators) are filtered."""
        yaml_with_nulls = """---
---
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
data:
  key: dmFsdWU=
---
"""
        processor = YamlPostProcessor(yaml_with_nulls)
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        docs = [d for d in docs if d is not None]
        assert len(docs) == 1
        assert docs[0]['kind'] == 'Secret'

    def test_unicode_content_preserved(self):
        """Test that unicode content is preserved after decoding."""
        unicode_content = "こんにちは世界"
        encoded = base64.b64encode(unicode_content.encode('utf-8')).decode()

        secret_yaml = f"""
apiVersion: v1
kind: Secret
metadata:
  name: unicode-secret
data:
  greeting: {encoded}
"""
        processor = YamlPostProcessor(secret_yaml)
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        assert docs[0]['data']['greeting'] == unicode_content

    def test_output_starts_with_document_separator(self):
        """Test that output starts with YAML document separator."""
        secret_yaml = """
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
data:
  key: dmFsdWU=
"""
        processor = YamlPostProcessor(secret_yaml)
        result = processor.decode_secrets()

        assert result.startswith('---\n')

    def test_binary_data_decode_failure(self):
        """Test that binary (non-UTF8) base64 data is preserved."""
        # Create base64 of binary data that's not valid UTF-8
        binary_data = bytes([0x80, 0x81, 0x82])
        encoded = base64.b64encode(binary_data).decode()

        secret_yaml = f"""
apiVersion: v1
kind: Secret
metadata:
  name: binary-secret
data:
  binary: {encoded}
"""
        processor = YamlPostProcessor(secret_yaml)
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        # Binary data should remain as original base64 since it can't decode to UTF-8
        assert docs[0]['data']['binary'] == encoded

    def test_special_characters_in_decoded_value(self):
        """Test decoding values with special YAML characters."""
        special_content = "key: value\nlist:\n  - item1\n  - item2"
        encoded = base64.b64encode(special_content.encode()).decode()

        secret_yaml = f"""
apiVersion: v1
kind: Secret
metadata:
  name: yaml-content-secret
data:
  nested_yaml: {encoded}
"""
        processor = YamlPostProcessor(secret_yaml)
        result = processor.decode_secrets()

        docs = list(yaml.safe_load_all(result))
        assert docs[0]['data']['nested_yaml'] == special_content


class TestYamlPostProcessorDumper:
    """Tests for YAML dumper behavior."""

    def test_multiline_string_in_non_secret_uses_literal_style(self):
        """Test that multiline strings in non-Secret resources use literal style."""
        configmap_yaml = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
data:
  config: |
    line1
    line2
    line3
"""
        processor = YamlPostProcessor(configmap_yaml)
        result = processor.decode_secrets()

        # The result should preserve the multiline format
        docs = list(yaml.safe_load_all(result))
        assert docs[0]['data']['config'] == "line1\nline2\nline3\n"
        # And use literal block style in output
        assert '|' in result

    def test_multiline_strings_use_literal_style(self):
        """Test that multiline strings use literal block style (|)."""
        multiline_value = "line1\nline2\nline3"
        encoded = base64.b64encode(multiline_value.encode()).decode()

        secret_yaml = f"""
apiVersion: v1
kind: Secret
metadata:
  name: multiline-secret
data:
  content: {encoded}
"""
        processor = YamlPostProcessor(secret_yaml)
        result = processor.decode_secrets()

        # The result should contain literal block style indicator
        assert '|' in result

    def test_keys_not_sorted(self):
        """Test that YAML keys maintain their original order."""
        secret_yaml = """
apiVersion: v1
kind: Secret
metadata:
  name: ordered-secret
data:
  zebra: emVicmE=
  alpha: YWxwaGE=
  beta: YmV0YQ==
"""
        processor = YamlPostProcessor(secret_yaml)
        result = processor.decode_secrets()

        # Parse and check order is maintained
        docs = list(yaml.safe_load_all(result))
        keys = list(docs[0]['data'].keys())
        assert keys == ['zebra', 'alpha', 'beta']
