import pytest
from proofops.config import Settings
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


@pytest.mark.parametrize(
    "values",
    [
        {"worker_concurrency": 0},
        {"worker_concurrency": 5},
        {"worker_poll_min_seconds": 2, "worker_poll_max_seconds": 1},
    ],
)
def test_worker_configuration_has_explicit_bounds(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
