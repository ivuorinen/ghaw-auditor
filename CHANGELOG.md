# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
