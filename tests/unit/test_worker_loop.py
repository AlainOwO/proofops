import logging
import threading
from unittest.mock import Mock

import pytest
from proofops.config import Settings
from proofops.workers import runner
from proofops.workers.runner import run_loop
from pydantic import ValidationError


def test_idle_polling_backs_off_with_a_bound_and_resets_after_work():
    class Stop:
        delays = []

        def is_set(self):
            return len(self.delays) == 6

        def wait(self, delay):
            self.delays.append(delay)

    results = iter([None, None, None, None, None, "job", None])
    stop = Stop()
    run_loop(Settings(_env_file=None), object(), stop, run=lambda **_: next(results))
    assert stop.delays == [0.5, 1, 2, 4, 5, 0.5]


def test_public_worker_loop_never_touches_a_factory_or_runner():
    def forbidden(**kwargs):
        raise AssertionError("public worker dispatched work")

    run_loop(Settings(_env_file=None, proofops_public_demo=True), None, None, run=forbidden)


def test_public_worker_entry_point_rejects_before_database_or_router_access(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("public worker accessed a private dependency"))
    monkeypatch.setattr(runner, "session_factory", forbidden)
    monkeypatch.setattr(runner, "claim_job", forbidden)
    monkeypatch.setattr(runner, "ModelRouter", forbidden)

    assert runner.run_once(settings=Settings(_env_file=None, proofops_public_demo=True)) is None
    forbidden.assert_not_called()


def test_unavailable_queue_backs_off_without_logging_exception_body(caplog):
    class Stop:
        def __init__(self):
            self.delays = []

        def is_set(self):
            return len(self.delays) == 7

        def wait(self, delay):
            self.delays.append(delay)

    stop = Stop()
    failure = Mock(side_effect=RuntimeError("synthetic-private-driver-body"))
    with caplog.at_level(logging.ERROR, logger=runner.__name__):
        run_loop(Settings(_env_file=None), object(), stop, run=failure)

    assert stop.delays == [0.5, 1, 2, 4, 5, 5, 5]
    assert failure.call_count == 7
    assert "RuntimeError" in caplog.text
    assert "synthetic-private-driver-body" not in caplog.text


def test_shutdown_after_inflight_job_prevents_another_claim():
    stop = threading.Event()

    def finish_job(**kwargs):
        stop.set()
        return "completed-job"

    run = Mock(side_effect=finish_job)
    run_loop(Settings(_env_file=None), object(), stop, run=run)
    run.assert_called_once()


def test_once_mode_does_not_retry_or_wait_after_queue_failure():
    stop = Mock()
    stop.is_set.return_value = False
    failure = Mock(side_effect=RuntimeError("queue unavailable"))

    run_loop(Settings(_env_file=None), object(), stop, once=True, run=failure)

    failure.assert_called_once()
    stop.wait.assert_not_called()


@pytest.mark.parametrize(
    "values",
    [
        {"worker_concurrency": 0},
        {"worker_concurrency": 5},
        {"worker_poll_min_seconds": 0},
        {"worker_poll_min_seconds": 5.1},
        {"worker_poll_max_seconds": 30.1},
        {"worker_poll_min_seconds": float("nan")},
        {"worker_poll_max_seconds": float("inf")},
        {"worker_poll_min_seconds": 2, "worker_poll_max_seconds": 1},
    ],
)
def test_worker_configuration_has_explicit_bounds(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
