import io
import re
import stat
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from proofops.config import APP_ROOT, Settings, get_settings
from proofops.domain.common import bytes_digest, canonical, digest, strict_json
from proofops.domain.schemas import (
    EvidenceRecord,
    Hash,
    Origin,
    RateCard,
    Record,
    ReviewInput,
    ReviewReport,
    ServiceContract,
    ServiceMap,
    UsageAssumptions,
    WorkloadRun,
)
from proofops.normalization.terraform import normalize
from proofops.policies.guards import TrustedRevision

INPUT_FILES = {
    "plan.json",
    "service-map.json",
    "contract.json",
    "rates.json",
    "usage.json",
    "evidence.json",
    "workloads.json",
}
EXPORT_FILES = {
    "sanitized-input.json",
    "report.json",
    "explanation.json",
    "trusted-revision.json",
    "schemas.json",
    "versions.json",
}
REPLAYS = {"valid-resize", "unsafe-resize", "incomplete-evidence"}


class Manifest(Record):
    origin: Origin
    reference_time: datetime
    files: dict[str, Hash] = Field(max_length=24)


def redact_text(value: str) -> str:
    value = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", value)
    value = re.sub(
        r"(?i)((?:api[_-]?key|password|secret|token)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", value
    )
    value = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[REDACTED]", value)
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED]", value)
    return value[:1000]


def bounded_zip(
    raw: bytes, allowed: set[str], settings: Settings | None = None
) -> dict[str, bytes]:
    settings = settings or get_settings()
    if len(raw) > settings.max_bundle_bytes:
        raise OverflowError("bundle exceeds compressed size limit")
    result: dict[str, bytes] = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > settings.max_bundle_files:
                raise OverflowError("bundle contains too many files")
            for entry in entries:
                name = entry.filename
                mode = entry.external_attr >> 16
                if name not in allowed or name in result or entry.is_dir() or stat.S_ISLNK(mode):
                    raise ValueError(
                        "bundle contains a duplicate, unsupported or unsafe archive path"
                    )
                if entry.flag_bits & 1:
                    raise ValueError("encrypted archives are unsupported")
                if entry.file_size > settings.max_artifact_bytes:
                    raise OverflowError("artifact exceeds expanded size limit")
                total += entry.file_size
                if total > settings.max_bundle_bytes:
                    raise OverflowError("bundle exceeds total expanded size limit")
                with archive.open(entry) as stream:
                    value = stream.read(settings.max_artifact_bytes + 1)
                if len(value) > settings.max_artifact_bytes or len(value) != entry.file_size:
                    raise OverflowError("artifact expanded beyond its declared size")
                result[name] = value
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:
        raise ValueError("invalid ZIP bundle") from exc
    return result


def verify_manifest(files: dict[str, bytes], expected: set[str]) -> tuple[Manifest, dict[str, Any]]:
    if set(files) != expected | {"manifest.json"}:
        raise ValueError("bundle must contain exactly its supported manifest and artifact files")
    manifest = Manifest.model_validate(strict_json(files["manifest.json"]))
    if set(manifest.files) != expected:
        raise ValueError("manifest must name exactly the supported artifact files")
    for name, hashed in manifest.files.items():
        if bytes_digest(files[name]) != hashed:
            raise ValueError(f"artifact hash mismatch: {name}")
    return manifest, {name: strict_json(files[name]) for name in expected}


def import_files(files: dict[str, bytes]) -> ReviewInput:
    manifest, documents = verify_manifest(files, INPUT_FILES)
    service_map = ServiceMap.model_validate(documents["service-map.json"])
    change = normalize(documents["plan.json"], service_map, manifest.files["plan.json"])
    # Metadata is an allowlist, never a channel for raw logs, secrets or arbitrary
    # attachments. Original bytes are hashed above and then discarded.
    if not isinstance(documents["evidence.json"], list) or not isinstance(
        documents["workloads.json"], list
    ):
        raise ValueError("evidence and workload artifacts must be JSON arrays")
    evidence = []
    for raw in documents["evidence.json"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("metadata", {}), dict):
            raise ValueError("each evidence record and its metadata must be an object")
        clean = dict(raw)
        clean["metadata"] = {
            key: redact_text(value) if isinstance(value, str) else value
            for key, value in raw.get("metadata", {}).items()
            if key
            in {
                "request_id",
                "query_status",
                "observed_count",
                "reason",
                "namespace",
                "cpu_units",
                "memory_mib",
                "image_digest",
                "task_definition_arn",
                "architecture",
                "os",
                "requires_fargate",
                "task_population_complete",
            }
        }
        clean["redaction_state"] = (
            "redacted" if clean["metadata"] != raw.get("metadata", {}) else "allowlisted"
        )
        evidence.append(EvidenceRecord.model_validate(clean))
    return ReviewInput(
        change=change,
        contract=ServiceContract.model_validate(documents["contract.json"]),
        rates=RateCard.model_validate(documents["rates.json"]),
        usage=UsageAssumptions.model_validate(documents["usage.json"]),
        evidence=evidence,
        workload_runs=[WorkloadRun.model_validate(item) for item in documents["workloads.json"]],
        reference_time=manifest.reference_time,
        origin=manifest.origin,
        input_hashes=manifest.files,
    )


def load_directory(path: Path) -> ReviewInput:
    settings = get_settings()
    path = path.resolve()
    if not path.is_relative_to(APP_ROOT) or any(
        part in {"evaluation", "evaluator_only", ".git"} for part in path.parts
    ):
        raise ValueError(
            "runtime bundle directories must be inside the application and outside evaluator storage"
        )
    files = {}
    for name in INPUT_FILES | {"manifest.json"}:
        source = path / name
        if source.is_symlink() or not source.is_file():
            raise ValueError("bundle contains a missing file or symlink")
        if source.stat().st_size > settings.max_artifact_bytes:
            raise OverflowError("artifact exceeds size limit")
        files[name] = source.read_bytes()
    if sum(len(item) for item in files.values()) > settings.max_bundle_bytes:
        raise OverflowError("bundle exceeds size limit")
    return import_files(files)


def load_replay(name: str) -> ReviewInput:
    if name not in REPLAYS:
        raise ValueError("unknown supplied replay")
    return load_directory(APP_ROOT / "fixtures/replays" / name)


def import_zip(raw: bytes) -> ReviewInput:
    return import_files(bounded_zip(raw, INPUT_FILES | {"manifest.json"}))


def export_report(
    bundle: ReviewInput, report: ReviewReport, explanation: dict, trusted: TrustedRevision
) -> bytes:
    from importlib.metadata import version

    from proofops.normalization.terraform import CPU_MEMORY_SOURCE

    values = {
        "sanitized-input.json": bundle,
        "report.json": report,
        "explanation.json": explanation,
        "trusted-revision.json": trusted,
        "schemas.json": {
            "ReviewInput": ReviewInput.model_json_schema(),
            "ReviewReport": ReviewReport.model_json_schema(),
        },
        "versions.json": {
            "application": "0.1.0",
            "engine_contract": "review-v1",
            "shape": "ecs-fargate-linux-v1",
            "fargate_mapping_source": CPU_MEMORY_SOURCE,
            "policy_template_hash": trusted.template_hash,
            "packages": {
                name: version(name)
                for name in ("fastapi", "pydantic", "sqlalchemy", "boto3", "openai", "anthropic")
            },
        },
    }
    files = {name: canonical(value) for name, value in values.items()}
    manifest = Manifest(
        origin=report.origin,
        reference_time=report.evaluation_reference_time,
        files={name: bytes_digest(raw) for name, raw in files.items()},
    )
    files["manifest.json"] = canonical(manifest)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, raw)
    return buffer.getvalue()


def replay_export(raw: bytes) -> tuple[ReviewReport, bool]:
    from proofops.domain.engine import review

    files = bounded_zip(raw, EXPORT_FILES | {"manifest.json"})
    expected = EXPORT_FILES if "versions.json" in files else EXPORT_FILES - {"versions.json"}
    _, documents = verify_manifest(files, expected)
    bundle = ReviewInput.model_validate(documents["sanitized-input.json"])
    saved = ReviewReport.model_validate(documents["report.json"])
    trusted = TrustedRevision.model_validate(documents["trusted-revision.json"])
    if saved.input_digest != digest(bundle) or saved.trusted_revision_hash != trusted.revision_hash:
        raise ValueError("report input or trusted-revision hash does not match")
    reproduced = review(
        bundle,
        trusted,
        review_id=saved.review_id,
        mode=saved.mode,
        reference=saved.evaluation_reference_time,
    )
    return reproduced, digest(saved) == digest(reproduced)
