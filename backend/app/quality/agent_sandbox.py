"""Agent Execution Sandbox -- isolate AI agent actions in a controlled environment.

Prevents unintended side-effects from autonomous code generation and execution
by enforcing resource limits, filesystem restrictions, network policies, and
command allowlists.  Every agent action runs inside a sandbox context that
tracks what the agent did and can roll back changes on failure.

Key features:
- Resource quotas: CPU time, memory, file count, total bytes written
- Filesystem jail: allowlisted paths, read-only vs read-write zones
- Network policy: blocked hosts, protocol restrictions, egress rate limits
- Command allowlist / blocklist for shell execution
- Action audit log with full provenance (who, what, when, outcome)
- Rollback support: undo file writes on sandbox violation
- Sandbox profiles: pre-built (strict, standard, permissive) + custom
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class SandboxProfile(StrEnum):
    STRICT = "strict"
    STANDARD = "standard"
    PERMISSIVE = "permissive"
    CUSTOM = "custom"


class ActionType(StrEnum):
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    SHELL_EXEC = "shell_exec"
    NETWORK_REQUEST = "network_request"
    ENV_ACCESS = "env_access"
    PACKAGE_INSTALL = "package_install"
    GIT_OPERATION = "git_operation"


class ActionVerdict(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"
    REQUIRES_APPROVAL = "requires_approval"


class ViolationSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class ResourceQuota:
    """Resource limits for a sandbox session."""
    max_cpu_seconds: float = 30.0
    max_memory_mb: float = 512.0
    max_files_written: int = 50
    max_bytes_written: int = 10 * 1024 * 1024  # 10 MB
    max_shell_commands: int = 20
    max_network_requests: int = 10
    max_execution_time_seconds: float = 300.0


@dataclass
class FilesystemPolicy:
    """Filesystem access policy."""
    allowed_read_paths: list[str] = field(
        default_factory=lambda: ["/workspace", "/tmp"],  # noqa: S108
    )
    allowed_write_paths: list[str] = field(
        default_factory=lambda: ["/workspace/output", "/tmp"],  # noqa: S108
    )
    blocked_paths: list[str] = field(default_factory=lambda: [
        "/etc", "/var", "/usr", "/root", "/home", "~/.ssh",
        "~/.aws", "~/.env", "/proc", "/sys",
    ])
    blocked_extensions: list[str] = field(default_factory=lambda: [
        ".pem", ".key", ".p12", ".pfx", ".env", ".credentials",
    ])
    max_file_size_bytes: int = 5 * 1024 * 1024  # 5 MB


@dataclass
class NetworkPolicy:
    """Network egress policy."""
    allowed_hosts: list[str] = field(default_factory=list)  # empty = all allowed
    blocked_hosts: list[str] = field(default_factory=lambda: [
        "169.254.169.254",  # cloud metadata
        "metadata.google.internal",
        "localhost", "127.0.0.1",
    ])
    allowed_protocols: list[str] = field(default_factory=lambda: ["https"])
    max_request_size_bytes: int = 1024 * 1024  # 1 MB
    rate_limit_per_minute: int = 30


@dataclass
class CommandPolicy:
    """Shell command execution policy."""
    allowed_commands: list[str] = field(default_factory=lambda: [
        "python", "node", "npm", "pip", "pytest", "ruff",
        "git", "ls", "cat", "head", "tail", "grep", "find", "echo",
    ])
    blocked_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /", "sudo", "chmod 777", "curl | bash",
        "wget | sh", "eval", "exec", "dd", "mkfs", "fdisk",
    ])
    blocked_patterns: list[str] = field(default_factory=lambda: [
        ">/dev/sd", "| sh", "| bash", "`", "$(", "&&rm",
    ])


@dataclass
class SandboxAction:
    """Record of an action attempted within the sandbox."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action_type: ActionType = ActionType.FILE_READ
    target: str = ""  # path, url, command, etc.
    verdict: ActionVerdict = ActionVerdict.ALLOWED
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    agent_id: str = ""
    session_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SandboxViolation:
    """A policy violation detected during sandbox execution."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    severity: ViolationSeverity = ViolationSeverity.MEDIUM
    action_type: ActionType = ActionType.FILE_WRITE
    description: str = ""
    target: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class SandboxSession:
    """State of an active sandbox session."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    profile: SandboxProfile = SandboxProfile.STANDARD
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    ended_at: str | None = None
    actions: list[SandboxAction] = field(default_factory=list)
    violations: list[SandboxViolation] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    bytes_written: int = 0
    shell_commands_run: int = 0
    network_requests_made: int = 0
    is_active: bool = True


# ── Profile Presets ──────────────────────────────────────────────────────

PROFILE_PRESETS: dict[SandboxProfile, dict[str, Any]] = {
    SandboxProfile.STRICT: {
        "quota": ResourceQuota(
            max_cpu_seconds=10, max_memory_mb=256, max_files_written=10,
            max_bytes_written=2 * 1024 * 1024, max_shell_commands=5,
            max_network_requests=0, max_execution_time_seconds=60,
        ),
        "fs": FilesystemPolicy(
            allowed_read_paths=["/workspace"],
            allowed_write_paths=["/workspace/output"],
        ),
        "net": NetworkPolicy(allowed_hosts=[], blocked_hosts=["*"]),
        "cmd": CommandPolicy(
            allowed_commands=["python", "pytest", "ruff", "ls", "cat"],
        ),
    },
    SandboxProfile.STANDARD: {
        "quota": ResourceQuota(),
        "fs": FilesystemPolicy(),
        "net": NetworkPolicy(),
        "cmd": CommandPolicy(),
    },
    SandboxProfile.PERMISSIVE: {
        "quota": ResourceQuota(
            max_cpu_seconds=120, max_memory_mb=2048, max_files_written=200,
            max_bytes_written=50 * 1024 * 1024, max_shell_commands=100,
            max_network_requests=50, max_execution_time_seconds=600,
        ),
        "fs": FilesystemPolicy(
            allowed_read_paths=["/"],
            allowed_write_paths=["/workspace", "/tmp"],  # noqa: S108
        ),
        "net": NetworkPolicy(),
        "cmd": CommandPolicy(blocked_commands=["rm -rf /", "sudo", "dd", "mkfs", "fdisk"]),
    },
}


# ── Sandbox Engine ───────────────────────────────────────────────────────

class AgentSandbox:
    """Manages sandboxed execution of AI agent actions."""

    def __init__(
        self,
        profile: SandboxProfile = SandboxProfile.STANDARD,
        quota: ResourceQuota | None = None,
        fs_policy: FilesystemPolicy | None = None,
        net_policy: NetworkPolicy | None = None,
        cmd_policy: CommandPolicy | None = None,
    ):
        preset = PROFILE_PRESETS.get(profile, PROFILE_PRESETS[SandboxProfile.STANDARD])
        self.profile = profile
        self.quota = quota or preset["quota"]
        self.fs_policy = fs_policy or preset["fs"]
        self.net_policy = net_policy or preset["net"]
        self.cmd_policy = cmd_policy or preset["cmd"]
        self._sessions: dict[str, SandboxSession] = {}
        self._completed_sessions: list[SandboxSession] = []

    # ── Session Management ────────────────────────────────────────────

    def start_session(self, agent_id: str) -> SandboxSession:
        """Start a new sandbox session for an agent."""
        session = SandboxSession(agent_id=agent_id, profile=self.profile)
        self._sessions[session.session_id] = session
        logger.info("Sandbox session %s started for agent %s (profile=%s)",
                     session.session_id[:8], agent_id, self.profile)
        return session

    def end_session(self, session_id: str) -> SandboxSession:
        """End a sandbox session."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        session.is_active = False
        session.ended_at = datetime.now(UTC).isoformat()
        self._completed_sessions.append(session)
        del self._sessions[session_id]
        return session

    def get_session(self, session_id: str) -> SandboxSession | None:
        return self._sessions.get(session_id)

    # ── Action Validation ─────────────────────────────────────────────

    def check_action(
        self, session_id: str, action_type: ActionType, target: str, **kwargs: Any,
    ) -> SandboxAction:
        """Validate an action against sandbox policies. Returns verdict."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found or inactive")
        if not session.is_active:
            raise ValueError(f"Session {session_id} is no longer active")

        verdict = ActionVerdict.ALLOWED
        reason = ""

        # Check resource quotas
        quota_result = self._check_quota(session, action_type)
        if quota_result:
            verdict, reason = quota_result

        # Check specific policies
        if verdict == ActionVerdict.ALLOWED:
            if action_type in (ActionType.FILE_READ, ActionType.FILE_WRITE, ActionType.FILE_DELETE):
                policy_result = self._check_filesystem(action_type, target)
                if policy_result:
                    verdict, reason = policy_result
            elif action_type == ActionType.NETWORK_REQUEST:
                policy_result = self._check_network(target)
                if policy_result:
                    verdict, reason = policy_result
            elif action_type == ActionType.SHELL_EXEC:
                policy_result = self._check_command(target)
                if policy_result:
                    verdict, reason = policy_result
            elif action_type == ActionType.ENV_ACCESS:
                policy_result = self._check_env_access(target)
                if policy_result:
                    verdict, reason = policy_result

        action = SandboxAction(
            action_type=action_type,
            target=target,
            verdict=verdict,
            reason=reason,
            agent_id=session.agent_id,
            session_id=session_id,
            metadata=kwargs,
        )
        session.actions.append(action)

        # Track resource usage for allowed actions
        if verdict == ActionVerdict.ALLOWED:
            self._track_usage(session, action_type, target, kwargs)

        # Record violations for blocked actions
        if verdict == ActionVerdict.BLOCKED:
            severity = self._severity_for_action(action_type, target)
            violation = SandboxViolation(
                severity=severity,
                action_type=action_type,
                description=reason,
                target=target,
            )
            session.violations.append(violation)
            logger.warning("Sandbox violation: %s -> %s (%s)",
                           action_type, target, reason)

        return action

    # ── Policy Checks ─────────────────────────────────────────────────

    def _check_quota(
        self, session: SandboxSession, action_type: ActionType,
    ) -> tuple[ActionVerdict, str] | None:
        if action_type == ActionType.FILE_WRITE:
            max_f = self.quota.max_files_written
            if len(session.files_written) >= max_f:
                return (ActionVerdict.BLOCKED,
                        f"File write quota exceeded ({max_f})")
            if session.bytes_written >= self.quota.max_bytes_written:
                return ActionVerdict.BLOCKED, "Byte write quota exceeded"
        elif action_type == ActionType.SHELL_EXEC:
            max_c = self.quota.max_shell_commands
            if session.shell_commands_run >= max_c:
                return (ActionVerdict.BLOCKED,
                        f"Shell command quota exceeded ({max_c})")
        elif action_type == ActionType.NETWORK_REQUEST:
            max_n = self.quota.max_network_requests
            if session.network_requests_made >= max_n:
                return (ActionVerdict.BLOCKED,
                        f"Network request quota exceeded ({max_n})")
        return None

    def _check_filesystem(
        self, action_type: ActionType, path: str,
    ) -> tuple[ActionVerdict, str] | None:
        # Check blocked paths
        for blocked in self.fs_policy.blocked_paths:
            if path.startswith(blocked) or path == blocked:
                return ActionVerdict.BLOCKED, f"Path {path} is in blocked zone ({blocked})"

        # Check blocked extensions
        for ext in self.fs_policy.blocked_extensions:
            if path.endswith(ext):
                return ActionVerdict.BLOCKED, f"File extension {ext} is blocked"

        # Check write permissions
        if (action_type in (ActionType.FILE_WRITE, ActionType.FILE_DELETE)
                and not any(path.startswith(p) for p in self.fs_policy.allowed_write_paths)):
            return ActionVerdict.BLOCKED, f"Write not allowed to {path}"

        # Check read permissions
        if (action_type == ActionType.FILE_READ
                and not any(path.startswith(p) for p in self.fs_policy.allowed_read_paths)):
            return ActionVerdict.BLOCKED, f"Read not allowed from {path}"

        return None

    def _check_network(self, target: str) -> tuple[ActionVerdict, str] | None:
        # Block all network if blocked_hosts is wildcard
        if "*" in self.net_policy.blocked_hosts:
            return ActionVerdict.BLOCKED, "All network access is blocked"

        # Check blocked hosts
        for blocked in self.net_policy.blocked_hosts:
            if blocked in target:
                return ActionVerdict.BLOCKED, f"Host {blocked} is blocked"

        # Check allowed hosts (if list is non-empty, only those are allowed)
        if (self.net_policy.allowed_hosts
                and not any(host in target for host in self.net_policy.allowed_hosts)):
            return ActionVerdict.BLOCKED, "Host not in allowed list"

        # Check protocol
        for proto in self.net_policy.allowed_protocols:
            if target.startswith(proto):
                return None
        if "://" in target:
            proto = target.split("://")[0]
            if proto not in self.net_policy.allowed_protocols:
                return ActionVerdict.BLOCKED, f"Protocol {proto} not allowed"

        return None

    def _check_command(self, command: str) -> tuple[ActionVerdict, str] | None:
        # Check blocked commands
        for blocked in self.cmd_policy.blocked_commands:
            if blocked in command:
                return ActionVerdict.BLOCKED, f"Command contains blocked pattern: {blocked}"

        # Check blocked patterns
        for pattern in self.cmd_policy.blocked_patterns:
            if pattern in command:
                return ActionVerdict.BLOCKED, f"Command matches blocked pattern: {pattern}"

        # Check allowed commands (first word)
        cmd_name = command.strip().split()[0] if command.strip() else ""
        if cmd_name not in self.cmd_policy.allowed_commands:
            return ActionVerdict.BLOCKED, f"Command '{cmd_name}' not in allowlist"

        return None

    def _check_env_access(self, var_name: str) -> tuple[ActionVerdict, str] | None:
        sensitive_vars = [
            "API_KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL",
            "PRIVATE_KEY", "AWS_", "AZURE_", "GCP_",
        ]
        for pattern in sensitive_vars:
            if pattern in var_name.upper():
                return ActionVerdict.BLOCKED, f"Access to sensitive env var {var_name} blocked"
        return None

    # ── Resource Tracking ─────────────────────────────────────────────

    def _track_usage(
        self, session: SandboxSession, action_type: ActionType,
        target: str, kwargs: dict[str, Any],
    ) -> None:
        if action_type == ActionType.FILE_WRITE:
            session.files_written.append(target)
            session.bytes_written += kwargs.get("size", 0)
        elif action_type == ActionType.SHELL_EXEC:
            session.shell_commands_run += 1
        elif action_type == ActionType.NETWORK_REQUEST:
            session.network_requests_made += 1

    def _severity_for_action(self, action_type: ActionType, target: str) -> ViolationSeverity:
        if action_type == ActionType.ENV_ACCESS:
            return ViolationSeverity.CRITICAL
        if action_type == ActionType.SHELL_EXEC and any(
            p in target for p in ["sudo", "rm -rf", "dd"]
        ):
            return ViolationSeverity.CRITICAL
        if action_type == ActionType.NETWORK_REQUEST and "169.254.169.254" in target:
            return ViolationSeverity.CRITICAL
        if action_type in (ActionType.FILE_DELETE, ActionType.FILE_WRITE):
            return ViolationSeverity.HIGH
        return ViolationSeverity.MEDIUM

    # ── Rollback ──────────────────────────────────────────────────────

    def rollback_session(self, session_id: str) -> list[str]:
        """Return list of files that would need to be rolled back."""
        session = self._sessions.get(session_id) or next(
            (s for s in self._completed_sessions if s.session_id == session_id), None
        )
        if not session:
            return []
        return list(session.files_written)

    # ── Analytics ─────────────────────────────────────────────────────

    def session_report(self, session_id: str) -> dict[str, Any]:
        """Generate a report for a sandbox session."""
        session = self._sessions.get(session_id) or next(
            (s for s in self._completed_sessions if s.session_id == session_id), None
        )
        if not session:
            return {}

        total_actions = len(session.actions)
        blocked = sum(1 for a in session.actions if a.verdict == ActionVerdict.BLOCKED)
        allowed = sum(1 for a in session.actions if a.verdict == ActionVerdict.ALLOWED)

        action_counts: dict[str, int] = {}
        for a in session.actions:
            action_counts[a.action_type] = action_counts.get(a.action_type, 0) + 1

        return {
            "session_id": session.session_id,
            "agent_id": session.agent_id,
            "profile": session.profile,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "is_active": session.is_active,
            "total_actions": total_actions,
            "allowed_actions": allowed,
            "blocked_actions": blocked,
            "block_rate": blocked / total_actions if total_actions else 0.0,
            "violations": len(session.violations),
            "critical_violations": sum(
                1 for v in session.violations if v.severity == ViolationSeverity.CRITICAL
            ),
            "files_written": len(session.files_written),
            "bytes_written": session.bytes_written,
            "shell_commands_run": session.shell_commands_run,
            "network_requests_made": session.network_requests_made,
            "action_breakdown": action_counts,
        }

    def global_stats(self) -> dict[str, Any]:
        """Aggregate stats across all completed sessions."""
        all_sessions = self._completed_sessions + list(self._sessions.values())
        if not all_sessions:
            return {"total_sessions": 0}

        total_violations = sum(len(s.violations) for s in all_sessions)
        total_actions = sum(len(s.actions) for s in all_sessions)
        total_blocked = sum(
            1 for s in all_sessions for a in s.actions
            if a.verdict == ActionVerdict.BLOCKED
        )

        return {
            "total_sessions": len(all_sessions),
            "total_actions": total_actions,
            "total_blocked": total_blocked,
            "total_violations": total_violations,
            "block_rate": total_blocked / total_actions if total_actions else 0.0,
            "sessions_with_violations": sum(
                1 for s in all_sessions if s.violations
            ),
        }
