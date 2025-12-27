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

## Supported Chart Sources

The application supports three types of Helm chart sources:

1. **Traditional Helm Repository** (HTTPS)
   - Uses `chart` field in application.yaml
   - Repository accessed via Helm repo add/update
   - Example: `https://argoproj.github.io/argo-helm`

2. **OCI Registry**
   - Uses `chart` field in application.yaml
   - Recognized by absence of `http://` or `https://` prefix
   - Example: `public.ecr.aws/karpenter`

3. **Git Repository**
   - Uses `path` field in application.yaml
   - Charts cached in `.chart_repo/{repo-name}` within the working directory
   - Git repo cloned once, reused on subsequent runs
   - `git fetch` only runs if revision checkout fails (lazy fetch)
   - Specific revision checked out via `git checkout`
   - Example: `https://github.com/argoproj/argo-helm` with `path: charts/argo-cd`

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

# Git scenario test
pytest tests/test_chart_git.py -v
```

### Test Scenarios

The test suite includes three scenarios:

1. **HTTPS Chart** (`tests/chart-https`)
   - Repository: `https://argoproj.github.io/argo-helm`
   - Chart: `argo-cd`
   - Version: `7.9.1`

2. **OCI Chart** (`tests/chart-oci`)
   - Repository: `public.ecr.aws/karpenter`
   - Chart: `karpenter`
   - Version: `1.5.2`

3. **Git Chart** (`tests/chart-git`)
   - Repository: `https://github.com/argoproj/argo-helm`
   - Path: `charts/argo-cd`
   - Revision: `argo-cd-9.2.1`

Each test:
1. Loads `application.yaml`
2. Extracts chart information
3. Downloads/retrieves the chart
4. Verifies directory structure and files are created

## Project Structure

- `argocd_helm_template.py` - Main script
- `pyproject.toml` - Project configuration and dependencies
- `tests/` - Test scenarios
  - `test_chart_https.py` - HTTPS repository test
  - `test_chart_oci.py` - OCI registry test
  - `chart-https/` - HTTPS test fixture
  - `chart-oci/` - OCI test fixture
