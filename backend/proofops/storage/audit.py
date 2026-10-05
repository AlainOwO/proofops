"""Identity/status-only authentication events, committed with their state change."""

from proofops.storage.database import AuditRow

HOST_OPERATOR = "host-operator"


def authentication_event(session, kind: str, *, actor: str, status: str, user_id=None) -> None:
    session.add(
        AuditRow(
            scope="authentication",
            kind=kind,
            actor=actor,
            data={"user_id": user_id, "status": status},
        )
    )
