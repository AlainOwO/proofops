import io
import json
import secrets
import zipfile
from time import monotonic

import pytest
from proofops.collectors.aws import AWSCollector
from proofops.config import APP_ROOT
from proofops.domain.common import bytes_digest
from proofops.domain.engine import review
from proofops.models.explanations import template_explanation
from proofops.storage.bundles import INPUT_FILES, export_report, import_files, redact_text


def credential_text(shape, marker):
    return {
        "json": json.dumps({"password": marker}),
        "escaped-json": json.dumps(json.dumps({"accessToken": marker})),
        "single-quoted": "{'api_key': '" + marker + "'}",
        "yaml-block": "password: |\n  " + marker + "\n  trailing words",
        "connection-url": "postgresql://account:" + marker + "@localhost/database",
        "http-userinfo": "https://account:" + marker + "@example.invalid/",
        "private-key": "-----BEGIN PRIVATE KEY-----\n" + marker + "\n-----END PRIVATE KEY-----",
        "bearer": "Authorization: Bearer " + marker,
        "cookie": "Cookie: session=" + marker,
        "spaced-value": "password=" + marker + " more words, and punctuation; end",
    }[shape]


@pytest.mark.parametrize(
    "shape",
    [
        "json",
        "escaped-json",
        "single-quoted",
        "yaml-block",
        "connection-url",
        "http-userinfo",
        "private-key",
        "bearer",
        "cookie",
        "spaced-value",
    ],
)
def test_credentials_suppress_the_entire_untrusted_value(shape):
    marker = secrets.token_urlsafe(24)
    assert redact_text(credential_text(shape, marker)) == "[REDACTED]"


def test_redaction_preserves_useful_nonsecret_text_and_output_bound():
    message = "Password must contain 14 to 128 characters. Collection is incomplete."
    assert redact_text(message) == message
    assert redact_text("x" * 1200) == "x" * 1000


def test_structured_credentials_do_not_survive_import_or_export(valid_bundle, trusted):
    root = APP_ROOT / "fixtures/replays/valid-resize"
    documents = {name: json.loads((root / name).read_text()) for name in INPUT_FILES}
    markers = [secrets.token_urlsafe(24) for _ in range(3)]
    documents["evidence.json"][0]["metadata"].update(
        reason=credential_text("json", markers[0]),
        request_id=credential_text("connection-url", markers[1]),
        query_status=credential_text("private-key", markers[2]),
    )
    files = {name: json.dumps(value).encode() for name, value in documents.items()}
    files["manifest.json"] = json.dumps(
        {
            "origin": "synthetic_fixture",
            "reference_time": valid_bundle.reference_time.isoformat(),
            "files": {name: bytes_digest(raw) for name, raw in files.items()},
        }
    ).encode()
    bundle = import_files(files)
    assert bundle.evidence[0].redaction_state == "redacted"
    assert all(marker not in bundle.model_dump_json() for marker in markers)
    report = review(bundle, trusted)
    raw = export_report(bundle, report, template_explanation(report), trusted)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert all(
            marker.encode() not in archive.read(name)
            for name in archive.namelist()
            for marker in markers
        )


def test_collected_json_log_credentials_are_suppressed(monkeypatch):
    marker = secrets.token_urlsafe(24)
    replies = iter(
        [
            {"queryId": "synthetic-query"},
            {
                "status": "Complete",
                "results": [[{"field": "@message", "value": credential_text("json", marker)}]],
            },
        ]
    )
    collector = AWSCollector({}, log_group="synthetic-log-group")
    collector.deadline = monotonic() + 5
    monkeypatch.setattr(collector, "call", lambda *args, **kwargs: next(replies))
    from proofops.domain.common import utcnow

    result = collector.log_source(utcnow(), utcnow())
    assert result.data["rows"] == [{"@message": "[REDACTED]"}]
