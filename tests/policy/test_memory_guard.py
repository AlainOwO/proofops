import pytest
from proofops.policies.fixtures import fixture_suite


@pytest.mark.policy
def test_actual_rego_fixture_suite(trusted):
    result = fixture_suite(trusted)
    assert result["passed"], result
    assert len(result["fixtures"]) == 10


@pytest.mark.policy
def test_always_deny_fails_healthy_fixtures(trusted, tmp_path):
    bad = tmp_path / "always_deny.rego"
    bad.write_text(
        'package proofops\nimport rego.v1\ndeny contains {"msg": "always deny"} if { true }\n'
    )
    result = fixture_suite(trusted, template=bad)
    assert not result["passed"]
    assert any(item["expected"] == "pass" and not item["passed"] for item in result["fixtures"])
