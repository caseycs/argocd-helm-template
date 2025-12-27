# ArgoCD Helm Template

Extract chart info from `application.yaml`, download Helm charts, and run `helm template`.

## Usage

```bash
uv run argocd_helm_template.py [--workdir DIR] [--chart-dir DIR] [--verbose] [--secrets] [additional helm template args]
```

### Options

- `--workdir DIR` - Working directory containing `application.yaml` and `values.yaml` (default: current directory)
- `--chart-dir DIR` - Directory to download charts to (default: `<workdir>/.chart`)
- `--verbose` - Enable verbose output
- `--secrets` - Decode base64 values in Secret resources and write to `.manifest.secrets.yaml`

### Example

```bash
uv run argocd_helm_template.py --workdir ./tests/chart-https --verbose
```

### Path-based Design

The application uses explicit paths rather than changing the working directory:
- Application expects `application.yaml` and `values.yaml` in the workdir
- All paths are resolved relative to the specified workdir
- No `os.chdir()` calls, making it suitable for libraries and concurrent operations

## Testing

### Setup

Install development dependencies:

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Run Tests

Run all tests:

```bash
pytest tests/ -v
```

Run specific scenario:

```bash
# HTTPS scenario test
pytest tests/test_chart_https.py -v

# OCI scenario test
pytest tests/test_chart_oci.py -v
```

### Test Scenarios

The test suite includes two scenarios:

1. **HTTPS Chart** (`tests/chart-https`)
   - Repository: `https://argoproj.github.io/argo-helm`
   - Chart: `argo-cd`
   - Version: `7.9.1`

2. **OCI Chart** (`tests/chart-oci`)
   - Repository: `public.ecr.aws/karpenter`
   - Chart: `karpenter`
   - Version: `1.5.2`

Each test:
1. Loads `application.yaml`
2. Extracts chart information
3. Downloads the chart
4. Verifies directory structure and files are created

## Project Structure

- `argocd_helm_template.py` - Main script
- `pyproject.toml` - Project configuration and dependencies
- `tests/` - Test scenarios
  - `test_chart_https.py` - HTTPS repository test
  - `test_chart_oci.py` - OCI registry test
  - `chart-https/` - HTTPS test fixture
  - `chart-oci/` - OCI test fixture
