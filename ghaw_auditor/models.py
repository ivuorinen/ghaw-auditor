"""Pydantic models for GitHub Actions and Workflows."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ActionType(StrEnum):
    """Type of action reference."""

    LOCAL = "local"
    GITHUB = "github"
    DOCKER = "docker"
    REUSABLE_WORKFLOW = "reusable_workflow"


class ActionRef(BaseModel):
    """Reference to an action with version info."""

    type: ActionType
    owner: str | None = None
    repo: str | None = None
    path: str | None = None
    ref: str | None = None  # Tag, branch, or SHA
    resolved_sha: str | None = None
    source_file: str
    source_line: int | None = None

    def canonical_key(self) -> str:
        """Generate unique key for deduplication."""
        if self.type == ActionType.LOCAL:
            return f"local:{self.path}"
        elif self.type == ActionType.DOCKER:
            return f"docker:{self.path}"
        elif self.type == ActionType.REUSABLE_WORKFLOW:
            return f"{self.owner}/{self.repo}/{self.path}@{self.resolved_sha or self.ref}"
        return f"{self.owner}/{self.repo}@{self.resolved_sha or self.ref}"


class ActionInput(BaseModel):
    """Action input definition."""

    name: str
    description: str | None = None
    required: bool = False
    default: str | bool | int | None = None


class ActionOutput(BaseModel):
    """Action output definition."""

    name: str
    description: str | None = None


class ActionManifest(BaseModel):
    """Parsed action.yml manifest."""

    name: str
    description: str | None = None
    author: str | None = None
    inputs: dict[str, ActionInput] = Field(default_factory=dict)
    outputs: dict[str, ActionOutput] = Field(default_factory=dict)
    runs: dict[str, Any] = Field(default_factory=dict)
    branding: dict[str, str] | None = None
    is_composite: bool = False
    is_docker: bool = False
    is_javascript: bool = False


class PermissionLevel(StrEnum):
    """Permission level."""

    NONE = "none"
    READ = "read"
    WRITE = "write"


class Permissions(BaseModel):
    """Job or workflow permissions."""

    actions: PermissionLevel | None = None
    checks: PermissionLevel | None = None
    contents: PermissionLevel | None = None
    deployments: PermissionLevel | None = None
    id_token: PermissionLevel | None = None
    issues: PermissionLevel | None = None
    packages: PermissionLevel | None = None
    pages: PermissionLevel | None = None
    pull_requests: PermissionLevel | None = None
    repository_projects: PermissionLevel | None = None
    security_events: PermissionLevel | None = None
    statuses: PermissionLevel | None = None


class Container(BaseModel):
    """Container configuration."""

    image: str
    credentials: dict[str, str] | None = None
    env: dict[str, str | int | float | bool] = Field(default_factory=dict)
    ports: list[int] = Field(default_factory=list)
    volumes: list[str] = Field(default_factory=list)
    options: str | None = None


class Service(BaseModel):
    """Service container configuration."""

    name: str
    image: str
    credentials: dict[str, str] | None = None
    env: dict[str, str | int | float | bool] = Field(default_factory=dict)
    ports: list[int] = Field(default_factory=list)
    volumes: list[str] = Field(default_factory=list)
    options: str | None = None


class Strategy(BaseModel):
    """Job matrix strategy."""

    matrix: dict[str, Any] = Field(default_factory=dict)
    fail_fast: bool = True
    max_parallel: int | None = None


class JobMeta(BaseModel):
    """Job metadata."""

    name: str
    runs_on: str | list[str]
    needs: list[str] = Field(default_factory=list)
    if_condition: str | None = Field(None, alias="if")
    permissions: Permissions | None = None
    environment: str | dict[str, Any] | None = None
    concurrency: str | dict[str, Any] | None = None
    timeout_minutes: int | None = None
    continue_on_error: bool = False
    container: Container | None = None
    services: dict[str, Service] = Field(default_factory=dict)
    strategy: Strategy | None = None
    # Reusable workflow fields
    uses: str | None = None  # Reusable workflow reference
    with_inputs: dict[str, Any] = Field(default_factory=dict)  # Inputs via 'with'
    secrets_passed: dict[str, str] | None = None  # Secrets passed to reusable workflow
    inherit_secrets: bool = False  # Whether secrets: inherit is used
    outputs: dict[str, Any] = Field(default_factory=dict)  # Job outputs
    # Action tracking
    actions_used: list[ActionRef] = Field(default_factory=list)
    secrets_used: set[str] = Field(default_factory=set)
    env_vars: dict[str, str | int | float | bool] = Field(default_factory=dict)


class ReusableContract(BaseModel):
    """Reusable workflow contract."""

    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)


class WorkflowMeta(BaseModel):
    """Workflow metadata."""

    name: str
    path: str
    triggers: list[str] = Field(default_factory=list)
    permissions: Permissions | None = None
    concurrency: str | dict[str, Any] | None = None
    env: dict[str, str | int | float | bool] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)
    jobs: dict[str, JobMeta] = Field(default_factory=dict)
    is_reusable: bool = False
    reusable_contract: ReusableContract | None = None
    secrets_used: set[str] = Field(default_factory=set)
    actions_used: list[ActionRef] = Field(default_factory=list)


class PolicyRule(BaseModel):
    """Policy rule."""

    name: str
    enabled: bool = True
    severity: str = "warning"  # warning, error
    config: dict[str, Any] = Field(default_factory=dict)


class Policy(BaseModel):
    """Audit policy configuration."""

    min_permissions: bool = True
    require_pinned_actions: bool = True
    forbid_branch_refs: bool = False
    allowed_actions: list[str] = Field(default_factory=list)
    denied_actions: list[str] = Field(default_factory=list)
    require_concurrency_on_pr: bool = False
    custom_rules: list[PolicyRule] = Field(default_factory=list)


class BaselineMeta(BaseModel):
    """Baseline metadata."""

    auditor_version: str
    commit_sha: str | None = None
    timestamp: datetime
    schema_version: str = "1.0"


class Baseline(BaseModel):
    """Baseline snapshot for diff mode."""

    meta: BaselineMeta
    actions: dict[str, ActionManifest]
    workflows: dict[str, WorkflowMeta]


class DiffEntry(BaseModel):
    """Single diff entry."""

    field: str
    old_value: Any = None
    new_value: Any = None
    change_type: str  # added, removed, modified


class ActionDiff(BaseModel):
    """Action diff."""

    key: str
    status: str  # added, removed, modified, unchanged
    changes: list[DiffEntry] = Field(default_factory=list)


class WorkflowDiff(BaseModel):
    """Workflow diff."""

    path: str
    status: str  # added, removed, modified, unchanged
    changes: list[DiffEntry] = Field(default_factory=list)


class AuditReport(BaseModel):
    """Complete audit report."""

    generated_at: datetime
    repository: str
    commit_sha: str | None = None
    actions: dict[str, ActionManifest]
    workflows: dict[str, WorkflowMeta]
    policy_violations: list[dict[str, Any]] = Field(default_factory=list)
