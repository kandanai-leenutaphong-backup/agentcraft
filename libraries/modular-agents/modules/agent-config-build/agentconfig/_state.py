from typing import Protocol


class OwnerDocumentStore(Protocol):
    def load(self, owner: str) -> tuple[dict[str, str], str | None]:
        """Return an isolated document copy and opaque CAS version; absence is ({}, None)."""
        ...

    def compare_exchange(self, owner: str, expected: str | None, documents: dict[str, str]) -> bool:
        """Atomically create-if-absent or replace-if-version-matches; conflict returns False.

        Acknowledged success must persist across instances/restarts. Unknown outcomes and
        unavailable storage raise; neither may return success or an empty load result.
        """
        ...