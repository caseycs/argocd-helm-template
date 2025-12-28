# ArgoCD Helm Template

A command-line tool to extract chart information from ArgoCD `application.yaml`, download Helm charts, and render Kubernetes manifests using `helm template`. Includes manifest diffing capabilities to compare changes between git references.

## When This Tool is Useful

### Use Case 1: Preview Manifest Changes Before Committing
Compare how your Kubernetes manifests will change when updating `application.yaml` or `values.yaml`:

```bash
# See what would change in your manifests
uv run argocd_helm_template.py diff --verbose
```

This generates two manifest files:
- `.manifest.yaml` - Current manifests with your pending changes
- `.diff/.manifest.yaml` - Original manifests from git HEAD

Then shows an interactive diff to review all changes.

### Use Case 2: AI-Assisted Chart Development with Instant Feedback
Get near-instant feedback when working with LLMs to develop or modify Helm chart values. Use this tool to validate chart rendering as you iterate:

```bash
# Quickly see how your values render into actual manifests
uv run argocd_helm_template.py render

# Edit values.yaml, then re-run to see the changes immediately
uv run argocd_helm_template.py render

# Compare your changes to see what actually changed
uv run argocd_helm_template.py diff --sort
```

Useful for:
- Iterating on chart values with an LLM assistant
- Validating that value changes produce expected manifest changes
- Debugging helm template issues in real-time
- Quickly prototyping chart configurations

This enables a fast feedback loop where you can ask an AI to modify values, immediately render the results, and provide feedback for refinement.

### Use Case 3: Review Resulting Manifest Diff Before Commit
Review how manifests differ between your current branch and production:

```bash
# Compare current changes against origin/main
uv run argocd_helm_template.py diff origin/main
```

Useful for:
- Code review: See exact manifest changes in pull requests
- Pre-deployment checks: Verify manifest changes before merging
- Debugging: Compare manifests between branches to find discrepancies

## Usage

The tool provides two main commands: `render` and `diff`.

```bash
# Render manifests
uv run argocd_helm_template.py render [OPTIONS] [additional helm template args]

# Compare manifests
uv run argocd_helm_template.py diff [REF] [OPTIONS] [additional helm template args]
```

### Common Options (available for both commands)

- `--workdir DIR` - Working directory containing application file and `values.yaml` (default: current directory)
- `--application FILE` - Application YAML filename (default: `application.yaml`)
- `--chart-dir DIR` - Directory to download charts to (default: `<workdir>/.chart`)
- `--verbose` - Enable verbose output, shows all git and helm commands
- `--secrets` - Decode base64 values in Secret resources and write to `.manifest.secrets.yaml`

### Render Command

Renders Kubernetes manifests from your `application.yaml` and `values.yaml`.

```bash
uv run argocd_helm_template.py render [OPTIONS] [additional helm template args]
```

### Diff Command

Compares manifests between your current state and a git reference.

```bash
uv run argocd_helm_template.py diff [REF] [OPTIONS] [additional helm template args]
```

- `REF` - Git reference to compare against (default: `HEAD`)
  - Examples: `HEAD`, `origin/main`, `--cached` (staged changes), `v1.0.0`
  - Shows interactive diff after rendering both versions

- `--sort` - Sort YAML keys alphabetically in manifests before diff
  - Reduces noise from key reordering
  - Makes diffs more readable

### Examples

#### Generate manifests (render command)
```bash
uv run argocd_helm_template.py render
```

#### Render with verbose output
```bash
uv run argocd_helm_template.py render --verbose
```

#### Render with decoded secrets
```bash
uv run argocd_helm_template.py render --secrets
```

#### Preview changes with verbose output
```bash
uv run argocd_helm_template.py diff --verbose
```

#### Compare against main branch with sorted output
```bash
uv run argocd_helm_template.py diff origin/main --sort
```

#### Show staged changes only (with sort)
```bash
uv run argocd_helm_template.py diff --cached --sort
```

#### Decode secrets and show diff
```bash
uv run argocd_helm_template.py diff --secrets
```

#### Render manifests from specific workdir
```bash
uv run argocd_helm_template.py render --workdir ./deployments/staging
```

#### Use custom application filename
```bash
uv run argocd_helm_template.py render --application my-application.yaml
uv run argocd_helm_template.py diff --application production.yaml
```

#### Pass extra helm template arguments
```bash
# Render with namespace override
uv run argocd_helm_template.py render --namespace myapp

# Diff with custom helm values
uv run argocd_helm_template.py diff origin/main --set image.tag=v1.2.3
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

## Installation

The script uses `uv` with embedded dependencies. No installation required - just run directly:

```bash
uv run argocd_helm_template.py --help
```

Required tools on your system:
- `helm` - For rendering charts
- `git` - For git operations
- `uv` - Python script runner
