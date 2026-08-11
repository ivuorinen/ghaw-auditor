# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **`--policy-file` is now actually loaded.** It was validated for existence and
  then discarded, so every user-authored rule silently fell back to the built-in
  defaults. A path that does not exist, is not valid YAML, is not a mapping, or
  fails schema validation is now a hard error instead of a silent downgrade.
- **`permissions: write-all` / `read-all` are no longer erased.** Bare-string
  permissions were parsed into an empty `Permissions()`, making the most
  permissive setting in GitHub Actions indistinguishable from declaring none.
  They now expand across every scope.
- **Reusable workflow calls are subject to policy.** `require_pinned_actions`,
  `forbid_branch_refs`, `allowed_actions` and `denied_actions` filtered on
  `ActionType.GITHUB` only, so `org/repo/.github/workflows/x.yml@main` passed
  every check.
- **`min_permissions` is implemented.** It was documented as enforcing
  least-privilege and defaulted to `true`, but nothing read it.
- **Policy violations are no longer double-counted.** `WorkflowMeta.actions_used`
  already contains every job's actions; the validator also iterated jobs.
- **`--enforce` exits 1, not 2.** `typer.Exit` subclasses `RuntimeError`, so the
  blanket `except Exception` rewrote every deliberate exit to 2.
- **`diff --baseline` detects modified actions.** `diff_actions` hardcoded
  `unchanged` for every action present in both sides.
- **A missing baseline fails the run** instead of logging and reporting success.
- **The disk cache and HTTP client are closed.** Neither was ever closed outside
  tests, leaking an sqlite connection and a connection pool per run.
- **No more temp-file leak.** Remote manifests were written to
  `NamedTemporaryFile(delete=False)` and unlinked only on the success path; they
  are now parsed from memory.
- **Server errors are no longer reported as missing manifests.** The
  `action.yml` -> `action.yaml` fallback swallowed every exception; only a real
  404 now advances. `tenacity` uses `reraise=True` so callers see the original
  `httpx` error rather than an opaque `RetryError`.
- **Action allow/deny patterns are globs, not raw regexes.** A `.` in a pattern
  matched any character (silently widening an allowlist) and an unbalanced
  bracket crashed the validator.
- **SHA pin detection accepts uppercase hex and SHA-256** (64-char) object ids.
- **Scanning no longer descends into `.git`, `.venv`, `node_modules`** and
  similar, which both dominated scan time and reported vendored third-party
  `action.yml` files as belonging to the audited repository.
- **A job without `runs-on` is no longer recorded as `ubuntu-latest`**, and an
  action manifest with a null `runs:` block no longer raises `AttributeError`.

### Added

- `--exclude <glob>` on `scan` (repeatable). `Scanner` already supported
  exclusions but nothing could reach them from the CLI.
- Resolved-action statistics in the analysis section (composite / docker /
  javascript counts, actions missing a description). `Analyzer.analyze_workflows`
  previously accepted the resolved manifests and discarded them.
- `LICENSE` file. The project declared MIT in metadata but shipped no terms.

### Changed

- **Breaking:** `PolicyValidator.validate(workflows, actions)` is now
  `validate(workflows)`. The second argument was never read.
- **Breaking:** `Policy.custom_rules` and the `PolicyRule` model are removed;
  nothing ever read them.
- Branch coverage is now measured (`--cov-branch`) and the floor is 100%
  (was 70%, line-only). Line coverage alone reported 100% while 18 branches
  were partial, which is how several of the defects above shipped green. Use
  `# pragma: no cover` for genuinely unreachable defensive code rather than
  lowering the floor.
- `Differ.diff_workflows` / `diff_actions`: the final `elif a and b` is now an
  `else`. The key comes from the union of both sides, so "in neither" cannot
  occur and the extra condition was an untestable branch.
- `GitHubClient`: the `elif 400 <= status_code < 600` log arm is now `else`.
  It is reached only from `raise_for_status`, so the code is 4xx/5xx by
  construction.

## [1.0.0] - 2025-10-02

### Added

- Initial release
- Full workflow and action scanning
- GitHub API integration with caching and retries
- Action reference resolution (local, GitHub, Docker)
- Monorepo action support (owner/repo/path@ref)
- Diff mode with baseline comparison
- Policy validation with enforcement
- JSON and Markdown report generation
- Comprehensive metadata extraction:
  - Triggers, permissions, concurrency
  - Jobs, steps, actions used
  - Secrets, environment variables
  - Containers, services, strategies
- `scan`, `inventory`, and `validate` commands
- uv-based dependency management
- Disk caching with configurable TTL
- Parallel API calls with configurable concurrency
- Reusable workflow detection and contract parsing
- Support for empty workflow_call declarations
- Robust error handling for malformed YAML

### Technical

- Python 3.11+ with type hints
- Pydantic v2 models
- ruamel.yaml parser
- httpx client with tenacity retries
- Rich console output
- Typer CLI framework
- diskcache for persistent caching
- Test coverage with pytest
