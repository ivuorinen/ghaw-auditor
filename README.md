# GitHub Actions & Workflows Auditor

A Python CLI tool for analyzing, auditing, and tracking
GitHub Actions workflows and actions.

## Features

- **Comprehensive Scanning**: Discovers workflows (`.github/workflows/*.yml`)
  and action manifests (`action.yml`)
- **Action Resolution**: Resolves GitHub action references to specific SHAs
  via GitHub API
- **Monorepo Support**: Handles monorepo actions like `owner/repo/path@ref`
- **Policy Validation**: Enforces security and best practice policies
- **Diff Mode**: Compare current state against baselines to track changes
  over time
- **Multiple Output Formats**: JSON and Markdown reports
- **Fast & Cached**: Uses `uv` for dependency management and disk caching
  for API responses
- **Rich Analysis**: Extracts triggers, permissions, secrets, runners,
  containers, services, and more

## Usage (Recommended)

Run directly with `uvx` without installation:

```bash
# Scan current directory
uvx ghaw-auditor scan

# Scan specific repository
uvx ghaw-auditor scan --repo /path/to/repo

# With GitHub token for better rate limits
GITHUB_TOKEN=ghp_xxx uvx ghaw-auditor scan --repo /path/to/repo

# List unique actions
uvx ghaw-auditor inventory --repo /path/to/repo

# Validate against policy
uvx ghaw-auditor validate --policy policy.yml --enforce
```

> **Note:** `uvx` runs the tool directly without installation.
> For frequent use or CI pipelines, see
> [Installation](#installation-optional) below.

## Installation (Optional)

### Using uv (recommended)

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone <repo-url>
cd ghaw_auditor
uv sync

# Install in editable mode
uv pip install -e .
```

### Using pipx

```bash
pipx install .
```

> **When to install:** Install locally if you use the tool frequently,
> need it in CI pipelines, or want faster execution (no download on each run).

## Commands

> **Note:** Examples use `uvx ghaw-auditor`.
> If installed locally, use `ghaw-auditor` directly.

### `scan` - Full Analysis

Analyzes workflows, resolves actions, generates reports.

```bash
# Basic scan
uvx ghaw-auditor scan --repo .

# Full scan with all options
uvx ghaw-auditor scan \
  --repo . \
  --output .audit \
  --format all \
  --token $GITHUB_TOKEN \
  --concurrency 8 \
  --write-baseline

# Offline mode (no API calls)
uvx ghaw-auditor scan --offline --format md
```

**Options:**

- `--repo <path>` - Repository path (default: `.`)
- `--token <str>` - GitHub token (env: `GITHUB_TOKEN`)
- `--output <dir>` - Output directory (default: `.ghaw-auditor`)
- `--format <json|md|all>` - Output format (default: `all`)
- `--cache-dir <dir>` - Cache directory
- `--offline` - Skip API resolution
- `--concurrency <int>` - API concurrency (default: 4)
- `--verbose`, `--quiet` - Logging levels

### `inventory` - List Actions

Print deduplicated action inventory.

```bash
uvx ghaw-auditor inventory --repo /path/to/repo

# Output:
# Unique Actions: 15
#   • actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8
#   • actions/setup-go@44694675825211faa026b3c33043df3e48a5fa00
#   ...
```

### `validate` - Policy Validation

Validate workflows against policies.

```bash
# Validate with default policy
uvx ghaw-auditor validate --repo .

# Validate with custom policy
uvx ghaw-auditor validate --policy policy.yml --enforce
```

**Options:**

- `--policy <file>` - Policy file path
- `--enforce` - Exit non-zero on violations

## Diff Mode

Track changes over time by comparing against baselines.

```bash
# Create initial baseline
uvx ghaw-auditor scan --write-baseline --output .audit

# Later, compare against baseline
uvx ghaw-auditor scan --diff --baseline .audit/baseline

# Output: .audit/diff/report.diff.md
```

**Baseline contents:**

- `baseline/actions.json` - Action inventory snapshot
- `baseline/workflows.json` - Workflow metadata snapshot
- `baseline/meta.json` - Auditor version, commit SHA, timestamp

**Diff reports show:**

- Added/removed/modified workflows
- Added/removed actions
- Changes to permissions, triggers, concurrency, secrets, etc.

## Output

The tool generates structured reports in the output directory:

### JSON Files

- **`actions.json`** - Deduplicated action inventory with manifests
- **`workflows.json`** - Complete workflow metadata
- **`violations.json`** - Policy violations

### Markdown Report

**`report.md`** includes:

- Summary (workflow count, action count, violations)
- Analysis (triggers, runners, secrets, permissions)
- Per-workflow details (jobs, actions used, configuration)
- Action inventory with inputs/outputs
- Policy violations

### Example Output

```text
.ghaw-auditor/
├── actions.json
├── workflows.json
├── violations.json
├── report.md
├── baseline/
│   ├── actions.json
│   ├── workflows.json
│   └── meta.json
└── diff/
    ├── actions.diff.json
    ├── workflows.diff.json
    └── report.diff.md
```

## Policy Configuration

Create `policy.yml` to enforce policies:

```yaml
require_pinned_actions: true      # Actions must use SHA refs
forbid_branch_refs: true          # Forbid branch refs (main, master, etc.)
require_concurrency_on_pr: true   # PR workflows must have concurrency

allowed_actions:                  # Whitelist
  - actions/*
  - github/*
  - docker/*

denied_actions:                   # Blacklist
  - dangerous/action

min_permissions: true             # Enforce least-privilege
```

**Policy rules:**

- `require_pinned_actions` - Actions must be pinned to SHA (not tags/branches)
- `forbid_branch_refs` - Forbid branch references (main, master, develop)
- `allowed_actions` - Whitelist of allowed actions (glob patterns)
- `denied_actions` - Blacklist of forbidden actions
- `require_concurrency_on_pr` - PR workflows must set concurrency groups

**Enforcement:**

```bash
# Warn on violations
uvx ghaw-auditor validate --policy policy.yml

# Fail CI on violations
uvx ghaw-auditor validate --policy policy.yml --enforce
# Exit code: 0 (pass), 1 (violations), 2 (error)
```

## Extracted Metadata

### Workflows

- Name, path, triggers (push, PR, schedule, etc.)
- Permissions (workflow & job-level)
- Concurrency groups
- Environment variables
- Reusable workflow contracts (inputs, outputs, secrets)

### Jobs

- Runner (`runs-on`)
- Dependencies (`needs`)
- Conditions (`if`)
- Timeouts
- Container & service configurations
- Matrix strategies
- Actions used per job

### Actions

- Type (GitHub, local, Docker)
- Resolved SHAs for GitHub actions
- Input/output definitions
- Runtime (composite, Docker, Node.js)
- Monorepo path support

### Security

- Secrets used (`${{ secrets.* }}`)
- Permissions (contents, packages, issues, etc.)
- Service containers (databases, caches)
- External actions (owner/repo resolution)

## Architecture

**Layers:**

- `cli` - Typer-based CLI interface
- `scanner` - File discovery
- `parser` - YAML parsing (ruamel.yaml)
- `resolver` - GitHub API integration
- `analyzer` - Pattern extraction
- `policy` - Policy validation
- `renderer` - JSON/Markdown reports
- `differ` - Baseline comparison
- `cache` - Disk-based caching
- `github_client` - HTTP client with retries

**Models (Pydantic):**

- `ActionRef`, `ActionManifest`
- `WorkflowMeta`, `JobMeta`
- `Permissions`, `Strategy`, `Container`, `Service`
- `Policy`, `Baseline`, `DiffEntry`

## Development

```bash
# Install dependencies
uv sync

# Run locally
uv run ghaw-auditor scan --repo .

# Run tests
uv run -m pytest

# Lint
uvx ruff check .

# Format
uvx ruff format .

# Type check
uvx mypy .

# Coverage
uv run -m pytest --cov --cov-report=html
```

## CI Integration

### GitHub Actions

```yaml
- name: Audit GitHub Actions
  run: |
    uvx ghaw-auditor scan --output audit-results
    uvx ghaw-auditor validate --policy policy.yml --enforce
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

- name: Upload Audit Results
  uses: actions/upload-artifact@v4
  with:
    name: audit-results
    path: audit-results/
```

> **Alternative:** For faster CI runs, cache the installation:
> `pip install ghaw-auditor` then use `ghaw-auditor` directly.

### Baseline Tracking

```yaml
- name: Compare Against Baseline
  run: |
    uvx ghaw-auditor scan --diff --baseline .audit/baseline
    cat .audit/diff/report.diff.md >> $GITHUB_STEP_SUMMARY
```

## Examples

### Analyze a Repository

```bash
uvx ghaw-auditor scan --repo ~/projects/myrepo
```

Output:

```text
Scanning repository...
Found 7 workflows and 2 actions
Parsing workflows...
Found 15 unique action references
Resolving actions...
Analyzing workflows...
Generating reports...
✓ Audit complete! Reports in .ghaw-auditor
```

### Track Changes Over Time

```bash
# Day 1: Create baseline
uvx ghaw-auditor scan --write-baseline

# Day 7: Check for changes
uvx ghaw-auditor scan --diff --baseline .ghaw-auditor/baseline

# View diff
cat .ghaw-auditor/diff/report.diff.md
```

### Validate Security Policies

```bash
# Check for unpinned actions
uvx ghaw-auditor validate --enforce

# Output:
# [ERROR] .github/workflows/ci.yml: Action actions/checkout
# is not pinned to SHA: v4
# Policy enforcement failed: 1 errors
```

### Generate Inventory

```bash
uvx ghaw-auditor inventory --repo . > actions-inventory.txt
```

## Performance

- **Parallel API calls** - Configurable concurrency (default: 4)
- **Disk caching** - API responses cached with TTL
- **Fast parsing** - Efficient YAML parsing with ruamel.yaml
- **Target**: 100+ workflows in < 60 seconds (with warm cache)

## Configuration

Optional `auditor.yaml` in repo root:

```yaml
exclude_paths:
  - "**/node_modules/**"
  - "**/vendor/**"

cache:
  dir: ~/.cache/ghaw-auditor
  ttl: 3600  # 1 hour

policies:
  require_pinned_actions: true
  forbid_branch_refs: true
```

## Troubleshooting

### Rate Limiting

```bash
# Set GitHub token for higher rate limits
export GITHUB_TOKEN=ghp_xxx
uvx ghaw-auditor scan
```

### Large Repositories

```bash
# Increase concurrency
uvx ghaw-auditor scan --concurrency 10

# Use offline mode for local analysis
uvx ghaw-auditor scan --offline
```

### Debugging

```bash
# Verbose output
uvx ghaw-auditor scan --verbose

# JSON logging for CI
uvx ghaw-auditor scan --log-json
```

## License

MIT

## Contributing

Contributions welcome! Please ensure:

- Tests pass: `uv run -m pytest`
- Code formatted: `uvx ruff format .`
- Linting clean: `uvx ruff check .`
- Type hints valid: `uvx mypy .`
- Coverage ≥ 85%
