import pytest
from proofops.policies.guards import load_trusted
from proofops.storage.bundles import load_replay


@pytest.fixture
def valid_bundle():
    return load_replay("valid-resize")


@pytest.fixture
def trusted():
    return load_trusted()
