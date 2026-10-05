import json
from uuid import uuid4

import pytest
from proofops.cli import main
from proofops.config import APP_ROOT


@pytest.mark.parametrize(
    ("scenario", "outcome", "code"),
    [
        ("valid-resize", "request_review", 0),
        ("unsafe-resize", "revise_change", 2),
        ("incomplete-evidence", "collect_evidence", 3),
    ],
)
def test_cli_review_and_replay_share_outcomes(scenario, outcome, code, capsys):
    output = APP_ROOT / "artifacts/cli-tests" / uuid4().hex
    assert (
        main(
            [
                "review",
                "--bundle",
                str(APP_ROOT / "fixtures/replays" / scenario),
                "--format",
                "json",
                "--output",
                str(output),
            ]
        )
        == code
    )
    assert json.loads(capsys.readouterr().out)["outcome"] == outcome
    assert outcome in (output / "summary.md").read_text()
    assert main(["replay", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["reproduced"]


def test_cli_evaluator_paths_rejected_without_reading(capsys):
    assert main(["review", "--bundle", str(APP_ROOT.parent / "data/evaluator_only")]) == 1
    assert "evaluator" in capsys.readouterr().out


def test_cli_trusted_map_cannot_be_changed_by_input(monkeypatch, valid_bundle, capsys):
    original = valid_bundle.change.service_map
    scope = original.scope.model_copy(update={"service": "another-service"})
    valid_bundle.change.service_map = original.model_copy(update={"scope": scope})
    monkeypatch.setattr("proofops.cli.load_directory", lambda _: valid_bundle)
    assert (
        main(
            [
                "review",
                "--bundle",
                "unused",
                "--trusted-map",
                str(APP_ROOT / "fixtures/replays/valid-resize/service-map.json"),
            ]
        )
        == 1
    )
    assert "trusted service map" in capsys.readouterr().out


def test_environment_rate_override_is_bound_and_explicit_flag_wins(monkeypatch, capsys):
    from proofops.config import get_settings
    from proofops.domain.common import bytes_digest

    directory = APP_ROOT / "artifacts/cli-tests" / uuid4().hex
    directory.mkdir(parents=True)
    original = APP_ROOT / "fixtures/replays/valid-resize/rates.json"
    overridden = directory / "rates.json"
    rates = json.loads(original.read_text())
    rates["price_per_vcpu_hour"] = "0.08"
    overridden.write_text(json.dumps(rates))
    monkeypatch.setenv("RATE_CARD_PATH", str(overridden))
    get_settings.cache_clear()
    try:
        arguments = [
            "review",
            "--bundle",
            str(original.parent),
            "--format",
            "json",
            "--output",
            str(directory / "report"),
        ]
        assert main(arguments) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["input_hashes"]["configured-rates.json"] == bytes_digest(
            overridden.read_bytes()
        )
        assert main([*arguments, "--rate-card", str(original)]) == 0
        explicit = json.loads(capsys.readouterr().out)
        assert explicit["input_hashes"]["configured-rates.json"] == bytes_digest(
            original.read_bytes()
        )
        assert report["cost"]["baseline_amount"] != explicit["cost"]["baseline_amount"]
    finally:
        get_settings.cache_clear()


def test_environment_rate_card_cannot_access_evaluator_data():
    from proofops.config import Settings
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="outside evaluator"):
        Settings(rate_card_path=APP_ROOT / "evaluation/evaluator_only/labels.json")
