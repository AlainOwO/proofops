from pathlib import Path
from unittest.mock import Mock

import pytest
from proofops.cli import main
from proofops.config import APP_ROOT, Settings
from proofops.storage import demo


@pytest.mark.parametrize("answer", ["", "n", "no", "anything"])
def test_reset_requires_explicit_confirmation(monkeypatch, capsys, answer):
    reset = Mock()
    monkeypatch.setattr(demo, "reset_demo_data", reset)
    prompt = Mock(return_value=answer)
    monkeypatch.setattr("builtins.input", prompt)
    assert main(["reset-demo-data"]) == 1
    prompt.assert_called_once()
    reset.assert_not_called()
    assert "cancelled; no data changed" in capsys.readouterr().out


@pytest.mark.parametrize("interruption", [EOFError, KeyboardInterrupt])
def test_reset_cancels_on_closed_or_interrupted_input(monkeypatch, capsys, interruption):
    reset = Mock()
    monkeypatch.setattr(demo, "reset_demo_data", reset)
    monkeypatch.setattr("builtins.input", Mock(side_effect=interruption))
    assert main(["reset-demo-data"]) == 1
    reset.assert_not_called()
    assert "cancelled" in capsys.readouterr().out


@pytest.mark.parametrize("answer", ["y", " YES "])
def test_reset_accepts_confirmation(monkeypatch, capsys, answer):
    reset = Mock(return_value={"deleted_reviews": 7, "reviews": []})
    monkeypatch.setattr(demo, "reset_demo_data", reset)
    monkeypatch.setattr("builtins.input", Mock(return_value=answer))
    assert main(["reset-demo-data"]) == 0
    reset.assert_called_once_with()
    assert "Removed 7 saved reviews" in capsys.readouterr().out


def test_yes_skips_the_prompt(monkeypatch, capsys):
    reset = Mock(
        return_value={
            "deleted_reviews": 0,
            "reviews": [
                {"scenario": "unsafe-resize", "outcome": "revise_change", "review_id": "demo"}
            ],
        }
    )
    monkeypatch.setattr(demo, "reset_demo_data", reset)
    prompt = Mock(side_effect=AssertionError("--yes must not prompt"))
    monkeypatch.setattr("builtins.input", prompt)
    assert main(["reset-demo-data", "--yes"]) == 0
    prompt.assert_not_called()
    reset.assert_called_once_with()
    assert "unsafe-resize: revise_change" in capsys.readouterr().out


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://remote.invalid/proofops",
        "postgresql+psycopg://127.0.0.1/research",
        "postgresql+psycopg://127.0.0.1/evaluation",
        "postgresql+psycopg://127.0.0.1/evaluator_only",
        "postgresql+psycopg:///proofops",
        "postgresql+psycopg://127.0.0.1/proofops?host=remote.invalid",
        "postgresql+psycopg://127.0.0.1/proofops?options=-csearch_path=evaluation",
        "sqlite:///artifacts/demo.db",
    ],
)
def test_reset_rejects_other_databases_before_reading_or_connecting(monkeypatch, url):
    factory = Mock(side_effect=AssertionError("must not open a database"))
    load = Mock(side_effect=AssertionError("must not load inputs"))
    monkeypatch.setattr(demo, "session_factory", factory)
    monkeypatch.setattr(demo, "load_trusted", load)
    settings = Settings(_env_file=None, database_url=url)
    with pytest.raises(ValueError, match="local proofops"):
        demo.reset_demo_data(settings=settings)
    factory.assert_not_called()
    load.assert_not_called()


@pytest.mark.parametrize("directory", ["evaluation", "research", "evaluator", "evaluator_only"])
def test_reset_rejects_protected_export_paths_before_reading(monkeypatch, directory):
    settings = Settings(_env_file=None).model_copy(
        update={"artifact_dir": APP_ROOT / "artifacts" / directory}
    )
    load = Mock(side_effect=AssertionError("must not load inputs"))
    monkeypatch.setattr(demo, "load_trusted", load)
    with pytest.raises(ValueError, match="outside protected data"):
        demo.reset_demo_data(settings=settings)
    load.assert_not_called()


def test_reset_rejects_symlinked_inputs_before_reading(monkeypatch):
    original = Path.resolve
    source = APP_ROOT / "fixtures/replays/valid-resize"

    def resolve(path, *args, **kwargs):
        if path == source:
            return APP_ROOT / "research"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    load = Mock(side_effect=AssertionError("must not read symlink targets"))
    monkeypatch.setattr(demo, "load_trusted", load)
    with pytest.raises(ValueError, match="without symlinks"):
        demo.reset_demo_data(settings=Settings(_env_file=None))
    load.assert_not_called()
