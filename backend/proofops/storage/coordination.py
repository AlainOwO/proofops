"""Short-lived, nonblocking work coordination using the existing PostgreSQL DB."""

from contextlib import contextmanager

from sqlalchemy import func, select

from proofops.domain.common import digest


@contextmanager
def try_work_lock(factory, namespace: str, key: str):
    # Transaction-scoped: a crash/rollback releases the lock. Never wait for a
    # provider request while occupying another API/worker execution slot.
    # A hash collision only declines duplicate work; it cannot reuse any data.
    identity = int(digest({"namespace": namespace, "key": key})[:16], 16) >> 1
    with factory.begin() as session:
        yield bool(session.scalar(select(func.pg_try_advisory_xact_lock(identity))))
