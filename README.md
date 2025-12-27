# ArgoCD Helm Template

A command-line tool to extract chart information from ArgoCD `application.yaml`, download Helm charts, and render Kubernetes manifests using `helm template`. Includes manifest diffing capabilities to compare changes between git references.

## When This Tool is Useful

### Use Case 1: Preview Manifest Changes Before Committing
Compare how your Kubernetes manifests will change when updating `application.yaml` or `values.yaml`:

```bash
# See what would change in your manifests
uv run argocd_helm_template.py --diff --verbose
```

This generates two manifest files:
- `.manifest.yaml` - Current manifests with your pending changes
- `.diff/.manifest.yaml` - Original manifests from git HEAD

Then shows an interactive diff to review all changes.

### Use Case 2: Compare Different Deployment Branches
Review how manifests differ between your current branch and production:

```bash
# Compare current changes against origin/main
uv run argocd_helm_template.py --diff origin/main
```

Useful for:
- Code review: See exact manifest changes in pull requests
- Pre-deployment checks: Verify manifest changes before merging
- Debugging: Compare manifests between branches to find discrepancies

### Use Case 3: Normalize YAML for Cleaner Diffs
Sort YAML keys alphabetically to reduce noise in diffs caused by inconsistent formatting:

```bash
# Show diff with sorted YAML keys (more readable)
uv run argocd_helm_template.py --diff --diff-sort
```

Useful for:
- Reducing spurious diffs from key reordering
- Making manifest comparisons more readable
- Focusing on actual changes vs. formatting changes

### Use Case 4: Generate Manifests for Deployment
Render final Kubernetes manifests to apply to a cluster:

```bash
# Generate manifests to stdout
uv run argocd_helm_template.py

# Apply directly to cluster
uv run argocd_helm_template.py | kubectl apply -f -
```

## Usage

```bash
uv run argocd_helm_template.py [OPTIONS] [additional helm template args]
```

### Common Options

- `--workdir DIR` - Working directory containing `application.yaml` and `values.yaml` (default: current directory)
- `--chart-dir DIR` - Directory to download charts to (default: `<workdir>/.chart`)
- `--verbose` - Enable verbose output, shows all git and helm commands
- `--secrets` - Decode base64 values in Secret resources and write to `.manifest.secrets.yaml`

### Diff Mode Options

- `--diff [REF]` - Compare manifests between current state and a git reference
  - Default: `HEAD` (latest commit)
  - Examples: `origin/main`, `--cached` (staged changes), `v1.0.0`
  - Shows interactive diff after rendering both versions

- `--diff-sort` - Sort YAML keys alphabetically in manifests before diff
  - Reduces noise from key reordering
  - Makes diffs more readable
  - Only applies when used with `--diff`

### Examples

#### Generate manifests (normal mode)
```bash
uv run argocd_helm_template.py
```

#### Preview changes with verbose output
```bash
uv run argocd_helm_template.py --diff --verbose
```

#### Compare against main branch with sorted output
```bash
uv run argocd_helm_template.py --diff origin/main --diff-sort
```

#### Show staged changes only
```bash
uv run argocd_helm_template.py --diff --cached --diff-sort
```

#### Decode secrets and show diff
```bash
uv run argocd_helm_template.py --diff --secrets
```

#### Render manifests from specific workdir
```bash
uv run argocd_helm_template.py --workdir ./deployments/staging
```

## How It Works

### Manifest Generation Flow

1. **Load Configuration** - Reads `application.yaml` and `values.yaml` from workdir
2. **Extract Chart Info** - Determines chart source (Helm repo, OCI registry, or Git)
3. **Download/Cache Chart** - Fetches chart if not cached locally
4. **Render Manifests** - Runs `helm template` with your configuration
5. **Output Manifests** - Writes `.manifest.yaml` to workdir and prints to stdout

### Diff Mode Flow

When using `--diff`:

1. Validates workdir is in a git repository
2. Checks for changes in `application.yaml` or `values.yaml`
3. Extracts original files from git reference to `.diff/` directory
4. Renders original manifests → `.diff/.manifest.yaml`
5. Renders current manifests → `.manifest.yaml`
6. Optionally sorts YAML keys (if `--diff-sort` used)
7. Shows interactive `git diff` between the two versions

## Supported Chart Sources

The tool supports three types of Helm chart sources:

### 1. Traditional Helm Repository (HTTPS)
- Uses `chart` field in `application.yaml`
- Repository accessed via `helm repo add/update`
- Example: `https://argoproj.github.io/argo-helm`

```yaml
spec:
  sources:
    - repoURL: https://argoproj.github.io/argo-helm
      chart: argo-cd
      targetRevision: 7.9.1
```

### 2. OCI Registry
- Uses `chart` field in `application.yaml`
- Recognized by absence of `http://` or `https://` prefix
- Example: `public.ecr.aws/karpenter`

```yaml
spec:
  sources:
    - repoURL: public.ecr.aws/karpenter
      chart: karpenter
      targetRevision: 1.5.2
```

### 3. Git Repository
- Uses `path` field in `application.yaml`
- Charts cached in `.chart_repo/{repo-name}` within workdir
- Git repo cloned once, reused on subsequent runs
- Specific revision checked out via `git checkout`
- Example: `https://github.com/argoproj/argo-helm` with `path: charts/argo-cd`

```yaml
spec:
  sources:
    - repoURL: https://github.com/argoproj/argo-helm
      path: charts/argo-cd
      targetRevision: argo-cd-9.2.1
```

## Design Principles

### Path-based (No Directory Changes)
The tool uses explicit paths rather than changing the working directory:
- All paths are resolved relative to the specified workdir
- No `os.chdir()` calls
- Safe for use in libraries and concurrent operations

### Git-aware Diffing
- Works within any git repository subdirectory
- Extracts original files from git references (HEAD, branches, tags)
- Supports staged changes with `--cached`
- Shows actual changes via interactive git diff

### Verbose Debugging
Enable `--verbose` to see all executed commands:
- Git commands for repository operations
- Helm commands for chart templating
- File operations and transformations

## Testing

### Run Tests

```bash
# All tests
pytest tests/ -v

# Specific scenarios
pytest tests/test_chart_https.py -v  # HTTPS repository
pytest tests/test_chart_oci.py -v    # OCI registry
pytest tests/test_chart_git.py -v    # Git repository
```

### Test Scenarios

1. **HTTPS Chart** (`tests/chart-https`)
   - Repository: `https://argoproj.github.io/argo-helm`
   - Chart: `argo-cd` v7.9.1

2. **OCI Chart** (`tests/chart-oci`)
   - Repository: `public.ecr.aws/karpenter`
   - Chart: `karpenter` v1.5.2

3. **Git Chart** (`tests/chart-git`)
   - Repository: `https://github.com/argoproj/argo-helm`
   - Path: `charts/argo-cd` revision `argo-cd-9.2.1`

## Project Structure

```
.
├── argocd_helm_template.py  # Main script
├── README.md                 # This file
├── pyproject.toml           # Project configuration
└── tests/                   # Test scenarios
    ├── test_chart_https.py  # HTTPS repository test
    ├── test_chart_oci.py    # OCI registry test
    ├── test_chart_git.py    # Git repository test
    ├── chart-https/         # HTTPS test fixture
    ├── chart-oci/           # OCI test fixture
    └── chart-git/           # Git test fixture
```

## Installation

The script uses `uv` with embedded dependencies. No installation required - just run directly:

```bash
uv run argocd_helm_template.py --help
```

Required tools on your system:
- `helm` - For rendering charts
- `git` - For git operations
- `uv` - Python script runner

## License

See LICENSE file for details.
