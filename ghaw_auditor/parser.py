"""YAML parser for workflow and action files."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from ghaw_auditor.models import (
    ActionInput,
    ActionManifest,
    ActionOutput,
    ActionRef,
    ActionType,
    Container,
    JobMeta,
    PermissionLevel,
    Permissions,
    ReusableContract,
    Service,
    Strategy,
    WorkflowMeta,
)

logger = logging.getLogger(__name__)


class Parser:
    """Parse workflow and action YAML files."""

    def __init__(self, repo_path: Path | None = None) -> None:
        """Initialize parser."""
        self.yaml = YAML(typ="safe")
        self.repo_path = repo_path or Path.cwd()

    def parse_workflow(self, path: Path) -> WorkflowMeta:
        """Parse a workflow file."""
        with open(path, encoding="utf-8") as f:
            content = f.read()
            data = self.yaml.load(content)

        if not data:
            raise ValueError(f"Empty workflow file: {path}")

        name = data.get("name", path.stem)
        triggers = self._extract_triggers(data.get("on", {}))
        permissions = self._parse_permissions(data.get("permissions"))
        env = data.get("env", {})
        concurrency = data.get("concurrency")
        defaults = data.get("defaults", {})

        # Check if reusable workflow
        is_reusable = "workflow_call" in triggers
        reusable_contract = None
        if is_reusable:
            on_data = data.get("on", {})
            if isinstance(on_data, dict) and "workflow_call" in on_data:
                call_data = on_data["workflow_call"]
                if call_data is not None:
                    reusable_contract = ReusableContract(
                        inputs=call_data.get("inputs", {}),
                        outputs=call_data.get("outputs", {}),
                        secrets=call_data.get("secrets", {}),
                    )

        # Parse jobs
        jobs = {}
        secrets_used: set[str] = set()
        actions_used: list[ActionRef] = []

        jobs_data = data.get("jobs")
        if jobs_data:
            for job_name, job_data in jobs_data.items():
                job_meta = self._parse_job(job_name, job_data, path, content)
                jobs[job_name] = job_meta
                secrets_used.update(job_meta.secrets_used)
                actions_used.extend(job_meta.actions_used)

        return WorkflowMeta(
            name=name,
            path=str(path.relative_to(self.repo_path)),
            triggers=triggers,
            permissions=permissions,
            concurrency=concurrency,
            env=env,
            defaults=defaults,
            jobs=jobs,
            is_reusable=is_reusable,
            reusable_contract=reusable_contract,
            secrets_used=secrets_used,
            actions_used=actions_used,
        )

    def _extract_triggers(self, on_data: Any) -> list[str]:
        """Extract trigger events from 'on' field."""
        if isinstance(on_data, str):
            return [on_data]
        elif isinstance(on_data, list):
            return on_data
        elif isinstance(on_data, dict):
            return list(on_data.keys())
        return []

    def _parse_permissions(self, perms: Any) -> Permissions | None:
        """Parse permissions."""
        if perms is None:
            return None
        if isinstance(perms, str):
            # Global read-all or write-all
            return Permissions()
        if isinstance(perms, dict):
            return Permissions(**{k: PermissionLevel(v) for k, v in perms.items() if v})
        return None

    def _parse_job(self, name: str, data: dict[str, Any] | None, path: Path, content: str) -> JobMeta:
        """Parse a job."""
        if data is None:
            data = {}

        # Check if this is a reusable workflow call
        uses = data.get("uses")
        is_reusable_call = uses is not None

        # runs-on is optional for reusable workflow calls
        runs_on = data.get("runs-on", "ubuntu-latest" if not is_reusable_call else "")

        needs = data.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]

        permissions = self._parse_permissions(data.get("permissions"))
        environment = data.get("environment")
        concurrency = data.get("concurrency")
        timeout_minutes = data.get("timeout-minutes")
        continue_on_error = data.get("continue-on-error", False)
        container = self._parse_container(data.get("container"))
        services = self._parse_services(data.get("services", {}))
        strategy = self._parse_strategy(data.get("strategy"))

        # Reusable workflow fields
        with_inputs = data.get("with", {})
        outputs = data.get("outputs", {})

        # Parse secrets for reusable workflows
        secrets_passed = None
        inherit_secrets = False
        secrets_data = data.get("secrets")
        if secrets_data == "inherit":
            inherit_secrets = True
        elif isinstance(secrets_data, dict):
            secrets_passed = secrets_data

        # Extract actions from steps or reusable workflow
        actions_used: list[ActionRef] = []
        secrets_used: set[str] = set()

        if is_reusable_call:
            # Parse reusable workflow reference
            assert isinstance(uses, str)  # Type guard: is_reusable_call ensures uses is not None
            workflow_ref = self._parse_reusable_workflow_ref(uses, path)
            actions_used.append(workflow_ref)
        else:
            # Parse actions from steps
            for step in data.get("steps", []):
                if step is None:
                    continue
                if "uses" in step:
                    action_ref = self._parse_action_ref(step["uses"], path)
                    actions_used.append(action_ref)

        # Extract secrets from entire job content
        secrets_used.update(self._extract_secrets(str(data)))

        job_data = {
            "name": name,
            "runs_on": runs_on,
            "needs": needs,
            "permissions": permissions,
            "environment": environment,
            "concurrency": concurrency,
            "timeout_minutes": timeout_minutes,
            "continue_on_error": continue_on_error,
            "container": container,
            "services": services,
            "strategy": strategy,
            "uses": uses,
            "with_inputs": with_inputs,
            "secrets_passed": secrets_passed,
            "inherit_secrets": inherit_secrets,
            "outputs": outputs,
            "actions_used": actions_used,
            "secrets_used": secrets_used,
            "env_vars": data.get("env", {}),
        }

        # Use alias for 'if' field
        if data.get("if") is not None:
            job_data["if"] = data.get("if")

        return JobMeta(**job_data)

    def _parse_action_ref(self, uses: str, source_file: Path) -> ActionRef:
        """Parse a 'uses' string into ActionRef."""
        uses = uses.strip()

        # Local action: ./path or ./.github/actions/name
        if uses.startswith("./"):
            return ActionRef(
                type=ActionType.LOCAL,
                path=uses,
                source_file=str(source_file),
            )

        # Docker action: docker://
        if uses.startswith("docker://"):
            return ActionRef(
                type=ActionType.DOCKER,
                path=uses,
                source_file=str(source_file),
            )

        # GitHub action: owner/repo@ref or owner/repo/path@ref
        match = re.match(r"^([^/]+)/([^/@]+)(?:/([^@]+))?@(.+)$", uses)
        if match:
            owner, repo, path, ref = match.groups()
            return ActionRef(
                type=ActionType.GITHUB,
                owner=owner,
                repo=repo,
                path=path or "action.yml",
                ref=ref,
                source_file=str(source_file),
            )

        raise ValueError(f"Invalid action reference: {uses}")

    def _parse_reusable_workflow_ref(self, uses: str, source_file: Path) -> ActionRef:
        """Parse a reusable workflow 'uses' string into ActionRef.

        Format: owner/repo/.github/workflows/workflow.yml@ref
        or: ./.github/workflows/workflow.yml (local)
        """
        uses = uses.strip()

        # Local reusable workflow
        if uses.startswith("./"):
            return ActionRef(
                type=ActionType.REUSABLE_WORKFLOW,
                path=uses,
                source_file=str(source_file),
            )

        # GitHub reusable workflow: owner/repo/path/to/workflow.yml@ref
        match = re.match(r"^([^/]+)/([^/@]+)/(.+\.ya?ml)@(.+)$", uses)
        if match:
            owner, repo, path, ref = match.groups()
            return ActionRef(
                type=ActionType.REUSABLE_WORKFLOW,
                owner=owner,
                repo=repo,
                path=path,
                ref=ref,
                source_file=str(source_file),
            )

        raise ValueError(f"Invalid reusable workflow reference: {uses}")

    def _parse_container(self, data: Any) -> Container | None:
        """Parse container configuration."""
        if data is None:
            return None
        if isinstance(data, str):
            return Container(image=data)
        return Container(
            image=data.get("image", ""),
            credentials=data.get("credentials"),
            env=data.get("env", {}),
            ports=data.get("ports", []),
            volumes=data.get("volumes", []),
            options=data.get("options"),
        )

    def _parse_services(self, data: dict[str, Any] | None) -> dict[str, Service]:
        """Parse services."""
        if data is None:
            return {}
        services = {}
        for name, svc_data in data.items():
            if isinstance(svc_data, str):
                services[name] = Service(name=name, image=svc_data)
            else:
                services[name] = Service(
                    name=name,
                    image=svc_data.get("image", ""),
                    credentials=svc_data.get("credentials"),
                    env=svc_data.get("env", {}),
                    ports=svc_data.get("ports", []),
                    volumes=svc_data.get("volumes", []),
                    options=svc_data.get("options"),
                )
        return services

    def _parse_strategy(self, data: Any) -> Strategy | None:
        """Parse strategy."""
        if data is None:
            return None
        return Strategy(
            matrix=data.get("matrix", {}),
            fail_fast=data.get("fail-fast", True),
            max_parallel=data.get("max-parallel"),
        )

    def _extract_secrets(self, content: str) -> set[str]:
        """Extract secret references from content."""
        secrets = set()
        # Match ${{ secrets.NAME }}
        pattern = r"\$\{\{\s*secrets\.(\w+)\s*\}\}"
        for match in re.finditer(pattern, content):
            secrets.add(match.group(1))
        return secrets

    def parse_action(self, path: Path) -> ActionManifest:
        """Parse an action.yml file."""
        with open(path, encoding="utf-8") as f:
            data = self.yaml.load(f)

        if not data:
            raise ValueError(f"Empty action file: {path}")

        name = data.get("name", path.parent.name)
        description = data.get("description")
        author = data.get("author")

        # Parse inputs
        inputs = {}
        for input_name, input_data in data.get("inputs", {}).items():
            if isinstance(input_data, dict):
                inputs[input_name] = ActionInput(
                    name=input_name,
                    description=input_data.get("description"),
                    required=input_data.get("required", False),
                    default=input_data.get("default"),
                )

        # Parse outputs
        outputs = {}
        for output_name, output_data in data.get("outputs", {}).items():
            if isinstance(output_data, dict):
                outputs[output_name] = ActionOutput(
                    name=output_name,
                    description=output_data.get("description"),
                )

        # Parse runs
        runs = data.get("runs", {})
        is_composite = runs.get("using") == "composite"
        is_docker = runs.get("using") in ("docker", "Dockerfile")
        is_javascript = runs.get("using", "").startswith("node")

        return ActionManifest(
            name=name,
            description=description,
            author=author,
            inputs=inputs,
            outputs=outputs,
            runs=runs,
            branding=data.get("branding"),
            is_composite=is_composite,
            is_docker=is_docker,
            is_javascript=is_javascript,
        )
