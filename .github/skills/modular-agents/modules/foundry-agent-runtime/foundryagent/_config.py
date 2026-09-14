"""FoundryConfig — the coordinates of a Foundry project, read once and frozen.

Module role:
    The single place this box reads the environment. Every other module takes a
    ``FoundryConfig`` instance; none of them calls ``os.environ``. That is what
    makes the box testable without a cloud account, and what stops a deployment
    behaving differently to a test because a variable was read twice at
    different times.

Why frozen:
    An agent runtime resolves its model per turn. If the config object were
    mutable, a retry loop could change the deployment underneath an in-flight
    request and the logs would attribute the result to the wrong model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any

# A Foundry *project* endpoint carries this path segment. An *account* endpoint
# does not, and is the single most common misconfiguration — see GOTCHAS.md G1.
_PROJECT_PATH_MARKER = "/api/projects/"

# Default environment prefix. Overridable so two Foundry projects can be wired
# into one process (primary + evaluation, say) without a naming collision.
DEFAULT_ENV_PREFIX = "FOUNDRY_"


@dataclass(frozen=True)
class FoundryConfig:
    """Where the model lives, and how hard to try when it refuses.

    Attributes:
        project_endpoint: The Foundry project endpoint, of the form
            ``https://<resource>.services.ai.azure.com/api/projects/<project>``.
        model_deployment: The default model deployment name. This is the name
            given to the *deployment*, which need not match the model name.
        model_deployment_fast: Optional cheaper/faster deployment. A spec whose
            model is the literal string ``"fast"`` resolves to this.
        api_version: Optional explicit API version. ``None`` leaves the SDK
            default, which is the right choice unless a specific version is
            being pinned for a reason worth writing down.
        fallback_models: Ordered deployments to try after the primary is
            rate-limited or refuses. Tried in order; empty means no fallback.
        max_retries: Attempts per model before moving to the next fallback.
    """

    project_endpoint: str
    model_deployment: str
    model_deployment_fast: str = ""
    api_version: str | None = None
    fallback_models: tuple[str, ...] = field(default_factory=tuple)
    max_retries: int = 3

    def __post_init__(self) -> None:
        """Reject the two values that cannot possibly work, and only those.

        Deliberately narrow. Shape problems that are *probably* wrong are
        reported by :meth:`warnings` instead, because a constructor that guesses
        is a constructor that blocks a legitimate endpoint form nobody
        anticipated.
        """
        if not self.project_endpoint:
            raise ValueError(
                "FoundryConfig requires a non-empty 'project_endpoint' — the "
                "Foundry project endpoint, e.g. "
                "https://<resource>.services.ai.azure.com/api/projects/<project>"
            )
        if not self.model_deployment:
            raise ValueError(
                "FoundryConfig requires a non-empty 'model_deployment' — the "
                "deployment name from the Foundry project, not the model name."
            )
        if not self.project_endpoint.startswith("https://"):
            raise ValueError(
                f"FoundryConfig 'project_endpoint' must be https:// — got "
                f"{self.project_endpoint!r}. Token-based auth will not be sent "
                f"over plaintext."
            )
        if self.max_retries < 1:
            raise ValueError("FoundryConfig 'max_retries' must be >= 1.")

    def warnings(self) -> list[str]:
        """Return non-fatal shape problems, most-likely-wrong first.

        Used by ``scripts/probe.py`` and safe to log at startup. Kept separate
        from ``__post_init__`` so a future endpoint form is a warning to
        investigate rather than a boot failure. See GOTCHAS.md G1.
        """
        problems: list[str] = []
        if _PROJECT_PATH_MARKER not in self.project_endpoint:
            problems.append(
                f"project_endpoint has no {_PROJECT_PATH_MARKER!r} segment — "
                f"this looks like an account endpoint, not a project endpoint. "
                f"Agent creation will fail with an authorization or 404 error "
                f"that does not mention the endpoint form (GOTCHAS.md G1)."
            )
        if self.project_endpoint.endswith("/"):
            problems.append(
                "project_endpoint has a trailing slash — some SDK versions "
                "produce a double-slash path that 404s."
            )
        if self.model_deployment in self.fallback_models:
            problems.append(
                f"model_deployment {self.model_deployment!r} also appears in "
                f"fallback_models — a rate-limited primary will be retried "
                f"against itself and the fallback buys nothing (GOTCHAS.md G8)."
            )
        return problems

    def model_queue(self) -> list[str]:
        """The ordered deployments to try: primary first, then fallbacks.

        Duplicates are dropped while preserving order, so a fallback list that
        repeats the primary degrades to "no fallback" rather than to a retry
        loop that cannot escape the deployment that is already refusing.
        """
        queue: list[str] = []
        for name in (self.model_deployment, *self.fallback_models):
            if name and name not in queue:
                queue.append(name)
        return queue

    def resolve_model(self, requested: str = "") -> str:
        """Resolve a per-agent model request to a concrete deployment name.

        ``""`` means "no preference" and yields the default deployment. The
        literal ``"fast"`` is an alias resolving to ``model_deployment_fast``,
        falling back to the default when no fast deployment is configured — so
        an alias is always safe to use even where it is not configured.
        """
        if not requested:
            return self.model_deployment
        if requested == "fast":
            return self.model_deployment_fast or self.model_deployment
        return requested

    def with_model(self, model_deployment: str) -> FoundryConfig:
        """Return a copy pointing at a different deployment.

        The retry/fallback loop needs a config per attempted model, and mutating
        the shared one would corrupt concurrent turns.
        """
        return replace(self, model_deployment=model_deployment)

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        *,
        prefix: str = DEFAULT_ENV_PREFIX,
    ) -> FoundryConfig:
        """Build from environment variables. The only env read in this box.

        Reads ``<prefix>PROJECT_ENDPOINT``, ``<prefix>MODEL_DEPLOYMENT``,
        ``<prefix>MODEL_DEPLOYMENT_FAST``, ``<prefix>API_VERSION`` and
        ``<prefix>FALLBACK_MODELS`` (comma-separated).

        Args:
            env: Mapping to read instead of ``os.environ``. Tests pass a dict;
                production passes nothing.
            prefix: Variable-name prefix, so a second project can be wired in.

        Raises:
            ValueError: With the exact variable names that are missing, because
                an error saying "endpoint required" costs a support round-trip
                that an error naming ``FOUNDRY_PROJECT_ENDPOINT`` does not.
        """
        source: Any = os.environ if env is None else env
        endpoint = (source.get(f"{prefix}PROJECT_ENDPOINT") or "").strip()
        deployment = (source.get(f"{prefix}MODEL_DEPLOYMENT") or "").strip()

        missing = [
            name
            for name, value in (
                (f"{prefix}PROJECT_ENDPOINT", endpoint),
                (f"{prefix}MODEL_DEPLOYMENT", deployment),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"FoundryConfig.from_env: missing required environment "
                f"variable(s): {', '.join(missing)}"
            )

        raw_fallbacks = (source.get(f"{prefix}FALLBACK_MODELS") or "").strip()
        fallbacks = tuple(
            part.strip() for part in raw_fallbacks.split(",") if part.strip()
        )
        api_version = (source.get(f"{prefix}API_VERSION") or "").strip() or None
        max_retries = (source.get(f"{prefix}MAX_RETRIES") or "").strip()

        return cls(
            project_endpoint=endpoint,
            model_deployment=deployment,
            model_deployment_fast=(
                source.get(f"{prefix}MODEL_DEPLOYMENT_FAST") or ""
            ).strip(),
            api_version=api_version,
            fallback_models=fallbacks,
            max_retries=int(max_retries) if max_retries else 3,
        )

    def redacted(self) -> dict[str, Any]:
        """A log-safe view. No credential ever enters this object, but the
        endpoint names a tenant's resource, so the host is kept and the project
        path is truncated."""
        host = self.project_endpoint.split("/api/")[0]
        return {
            "endpoint_host": host,
            "model_deployment": self.model_deployment,
            "model_deployment_fast": self.model_deployment_fast or None,
            "api_version": self.api_version,
            "fallback_models": list(self.fallback_models),
            "max_retries": self.max_retries,
        }


__all__ = ["FoundryConfig", "DEFAULT_ENV_PREFIX"]
