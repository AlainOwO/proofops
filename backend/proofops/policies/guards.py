from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from proofops.config import APP_ROOT
from proofops.domain.common import bytes_digest, digest, strict_json
from proofops.domain.schemas import (
    Hash,
    Label,
    Positive,
    Record,
    ReviewInput,
    Scope,
    ServiceContract,
)


class GuardSpec(Record):
    guard_id: Label
    revision: Positive
    kind: Literal["ecs_task_memory_floor"] = "ecs_task_memory_floor"
    service_contract_id: Label
    minimum_task_memory_mib: Positive
    incident_id: Label
    repair_reference: Label
    approved_bound_fact_id: Literal["approved.minimum_task_memory_mib"] = (
        "approved.minimum_task_memory_mib"
    )
    rationale_fact_ids: list[Literal["incident.repair_verified"]]
    owner: Label
    reviewer: Label
    state: Literal["draft", "fixtures_passed", "approved_in_trusted_revision", "active"]
    approval_reference: Label
    contract_hash: Hash


class ExceptionSpec(Record):
    exception_id: Label
    owner: Label
    reason: Label
    scope: Scope
    candidate_commit: Label
    guard_revision: Positive
    expires_at: datetime


class TrustedRevision(Record):
    contract: ServiceContract
    guard: GuardSpec
    exceptions: list[ExceptionSpec] = Field(default_factory=list, max_length=20)
    template_hash: Hash | None = None

    @property
    def revision_hash(self) -> str:
        # Preserve the identity of old exported snapshots. Fresh enforcing
        # revisions loaded below must include an explicit template hash.
        return digest(
            self
            if self.template_hash is not None
            else self.model_dump(mode="json", exclude={"template_hash"})
        )


def load_trusted(path: Path | None = None) -> TrustedRevision:
    source = path or APP_ROOT / "policies/approved/reports-demo.json"
    source = source.resolve()
    if not source.is_relative_to(APP_ROOT) or any(
        part in {"evaluation", "evaluator_only", ".git"}
        for part in source.relative_to(APP_ROOT).parts
    ):
        raise ValueError(
            "trusted policy must be inside this application checkout and outside evaluator storage"
        )
    if source.stat().st_size > 1_048_576:
        raise ValueError("trusted policy exceeds its size bound")
    revision = TrustedRevision.model_validate(strict_json(source.read_bytes()))
    expected_template = bytes_digest(
        (APP_ROOT / "policies/templates/ecs_task_memory_floor.rego").read_bytes()
    )
    if revision.template_hash != expected_template:
        raise ValueError("trusted revision must bind the exact reviewed policy template hash")
    if revision.guard.contract_hash != digest(revision.contract):
        raise ValueError("trusted guard's contract hash does not match its contract")
    if revision.guard.minimum_task_memory_mib != revision.contract.minimum_task_memory_mib:
        raise ValueError("trusted guard and approved contract bound disagree")
    if revision.guard.service_contract_id != revision.contract.contract_id:
        raise ValueError("trusted guard contract identity mismatch")
    return revision


def applicability(bundle: ReviewInput, trusted: TrustedRevision) -> bool:
    after = bundle.change.after
    app = trusted.contract.applicability
    return bool(
        after
        and bundle.change.service_map.scope == trusted.contract.scope
        and after.image_digest == app.image_digest
        and after.non_resize_config_hash == app.non_resize_config_hash
        and bundle.contract.applicability.workload_profile_hash == app.workload_profile_hash
        and bundle.contract.applicability.dependency_state_hash == app.dependency_state_hash
    )


def valid_exception(
    bundle: ReviewInput, trusted: TrustedRevision, reference: datetime
) -> ExceptionSpec | None:
    return next(
        (
            item
            for item in trusted.exceptions
            if item.expires_at > reference
            and item.scope == trusted.contract.scope
            and item.candidate_commit == bundle.change.service_map.candidate_commit
            and item.guard_revision == trusted.guard.revision
        ),
        None,
    )


def draft_from_approved(trusted: TrustedRevision) -> GuardSpec:
    return trusted.guard.model_copy(update={"state": "draft"})


def validate_proposal(proposal: dict, trusted: TrustedRevision) -> GuardSpec:
    parsed = GuardSpec.model_validate(proposal)
    expected = draft_from_approved(trusted)
    if parsed != expected:
        raise ValueError("proposal must preserve the exact approved facts, scope and draft state")
    return parsed
