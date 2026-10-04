from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Count = Annotated[int, Field(strict=True, ge=0, le=1_000_000_000)]
Positive = Annotated[int, Field(strict=True, gt=0, le=1_000_000_000)]
Money = Annotated[Decimal, Field(allow_inf_nan=False, max_digits=32, decimal_places=16)]
Nonnegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Label = Annotated[str, Field(min_length=1, max_length=200)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, str_max_length=4096)
    schema_version: Literal[1] = 1

    @field_validator("*", mode="after")
    @classmethod
    def aware_times(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("timestamps must include a UTC offset")
            return value.astimezone(UTC)
        return value


class Origin(StrEnum):
    SYNTHETIC = "synthetic_fixture"
    BENCHMARK = "benchmark"
    LOCAL = "local_observation"
    AWS = "aws_observation"


class Outcome(StrEnum):
    REVISE = "revise_change"
    COLLECT = "collect_evidence"
    REVIEW = "request_review"
    OUT = "out_of_scope"


class Scope(Record):
    account_id: Annotated[str, Field(pattern=r"^\d{12}$")]
    region: Annotated[str, Field(pattern=r"^[a-z]{2}(?:-[a-z]+)+-\d+$")]
    cluster: Label
    service: Label
    terraform_address: Annotated[str, Field(min_length=1, max_length=512)]
    environment: Label


class Applicability(Record):
    image_digest: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
    workload_profile_hash: Hash
    dependency_state_hash: Hash
    non_resize_config_hash: Hash


class Requirements(Record):
    min_correct_requests_per_run: Positive = 10000
    max_p95_latency_ms: Nonnegative = Decimal("250")
    max_http_failure_rate_exclusive: Annotated[Decimal, Field(gt=0, le=1, allow_inf_nan=False)] = (
        Decimal("0.01")
    )
    max_incorrect_successful_responses: Count = 0
    max_dropped_iterations: Count = 0
    max_restarts: Count = 0
    required_repetitions: Annotated[int, Field(strict=True, ge=1, le=10)] = 3
    max_evidence_age_seconds: Positive = 86400
    required_sources: list[Label] = Field(
        default_factory=lambda: [
            "terraform",
            "task_configuration",
            "workload_baseline",
            "workload_candidate",
        ],
        max_length=12,
    )


class ServiceContract(Record):
    contract_id: Label
    owner: Label
    revision: Positive
    scope: Scope
    applicability: Applicability
    minimum_task_memory_mib: Positive
    approval_reference: Label
    origin: Origin
    requirements: Requirements


class ServiceMap(Record):
    scope: Scope
    repository: Label
    base_commit: Annotated[str, Field(pattern=r"^[a-f0-9]{40,64}$")]
    candidate_commit: Annotated[str, Field(pattern=r"^[a-f0-9]{40,64}$")]


class TaskConfiguration(Record):
    cpu_units: Positive | None
    memory_mib: Positive | None
    os: str | None
    architecture: str | None
    image_digest: str | None
    config_hash: Hash
    non_resize_config_hash: Hash


class ChangeSet(Record):
    source_hash: Hash
    service_map: ServiceMap
    address: str | None
    actions: list[str]
    before: TaskConfiguration | None
    after: TaskConfiguration | None
    unknown_paths: list[str] = Field(default_factory=list)
    sensitive_paths: list[str] = Field(default_factory=list)
    shape_version: Literal["ecs-fargate-linux-v1"] = "ecs-fargate-linux-v1"
    supported: bool
    applicable_resource: bool
    normalization_findings: list[str] = Field(default_factory=list)


class EvidenceRecord(Record):
    evidence_id: Label
    kind: Label
    source: Label
    scope: Scope
    resource_revision: Label
    observed_start: datetime
    observed_end: datetime
    collected_at: datetime
    collection_status: Literal[
        "complete", "pending", "denied", "failed", "not_configured", "not_requested"
    ]
    units: Label
    population: Label
    sample_count: Count | None
    content_hash: Hash
    redaction_state: Literal["allowlisted", "redacted"] = "allowlisted"
    origin: Origin
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict, max_length=12)

    @model_validator(mode="after")
    def ordered(self) -> "EvidenceRecord":
        if self.observed_end < self.observed_start or self.collected_at < self.observed_end:
            raise ValueError("evidence window must end before collection")
        return self


class RateCard(Record):
    rate_id: Label
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    price_date: datetime
    retrieved_at: datetime
    source_url: Annotated[str, Field(max_length=1000)]
    region: Label
    architecture: Literal["X86_64", "ARM64"]
    os: Literal["LINUX"]
    purchase_option: Literal["on_demand"]
    price_per_vcpu_hour: Nonnegative | None
    price_per_gib_hour: Nonnegative | None
    origin: Origin
    billing_minimum_seconds: Positive = 60
    billing_granularity_seconds: Positive = 1


class UsageAssumptions(Record):
    baseline_task_hours: Nonnegative | None
    candidate_task_hours: Nonnegative | None
    basis: Literal["explicit_projection", "observed_allocation"]
    window_start: datetime
    window_end: datetime
    assumptions: list[Label] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def ordered(self) -> "UsageAssumptions":
        if self.window_end <= self.window_start:
            raise ValueError("cost window must have positive duration")
        return self


class ClassResult(Record):
    completed: Count
    correct: Count
    p95_latency_ms: Nonnegative | None

    @model_validator(mode="after")
    def counts(self) -> "ClassResult":
        if self.correct > self.completed:
            raise ValueError("correct responses exceed completed responses")
        return self


class WorkloadRun(Record):
    run_id: Label
    role: Literal["baseline", "candidate"]
    scope: Scope
    image_digest: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
    config_hash: Hash
    non_resize_config_hash: Hash
    profile_hash: Hash
    dependency_hash: Hash
    environment: Label
    platform: Label
    started_at: datetime
    ended_at: datetime
    warmup_policy: Label
    offered: Count
    completed: Count
    correct: Count
    http_failures: Count
    incorrect_successful_responses: Count
    dropped_iterations: Count
    restarts: Count
    p95_latency_ms: Nonnegative | None
    request_classes: dict[Literal["small", "medium", "large"], ClassResult]
    terminal_status: Literal["completed", "interrupted", "failed"]
    origin: Origin

    @model_validator(mode="after")
    def consistent(self) -> "WorkloadRun":
        if self.ended_at <= self.started_at:
            raise ValueError("workload must have a positive duration")
        if (
            self.correct + self.http_failures + self.incorrect_successful_responses
            != self.completed
        ):
            raise ValueError("correct, failed and incorrect responses must reconcile to completed")
        if self.completed + self.dropped_iterations > self.offered:
            raise ValueError("completed and dropped work exceeds offered work")
        if sum(item.completed for item in self.request_classes.values()) != self.completed:
            raise ValueError("per-class completed counts must reconcile")
        if sum(item.correct for item in self.request_classes.values()) != self.correct:
            raise ValueError("per-class correct counts must reconcile")
        return self


class Finding(Record):
    code: Label
    severity: Literal["violation", "missing", "info", "unsupported"]
    message: Annotated[str, Field(max_length=1200)]
    fact_ids: list[str] = Field(default_factory=list)


class CostEstimate(Record):
    currency: str
    rate_id: str
    price_date: datetime
    source_url: str
    basis: str
    region: str
    os: str
    architecture: str
    purchase_option: str
    baseline_task_hours: Nonnegative | None
    candidate_task_hours: Nonnegative | None
    baseline_amount: Money | None
    candidate_amount: Money | None
    projected_difference: Money | None
    projected_reduction_fraction: Decimal | None
    covered: list[str]
    excluded: list[str]
    assumptions: list[str]
    complete: bool
    origin: Origin
    cost_per_correct_request: dict[str, str | None] = Field(default_factory=dict)


class ReviewInput(Record):
    change: ChangeSet
    contract: ServiceContract
    rates: RateCard
    usage: UsageAssumptions
    evidence: list[EvidenceRecord] = Field(max_length=100)
    workload_runs: list[WorkloadRun] = Field(max_length=20)
    reference_time: datetime
    origin: Origin
    input_hashes: dict[str, Hash]


class Fact(Record):
    fact_id: Label
    value: str | int | bool | None
    kind: Label


class ReviewReport(Record):
    review_id: Label
    engine_version: Literal["1.0"] = "1.0"
    input_hashes: dict[str, Hash]
    input_digest: Hash
    trusted_revision_hash: Hash | None
    evaluation_reference_time: datetime
    mode: Literal["replay", "live"]
    origin: Origin
    outcome: Outcome
    findings: list[Finding]
    coverage: dict[str, Any]
    cost: CostEstimate | None
    performance: dict[str, Any]
    facts: list[Fact]
    required_citations: list[str]
    next_steps: list[str]
    change: ChangeSet
    contract_revision: Positive


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact_id: str = Field(max_length=200)
    value: str | int | float | bool | None


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=1400)
    finding_codes: list[str] = Field(max_length=50)
    cited_facts: list[Citation] = Field(max_length=12)
    next_step: Literal["revise_change", "collect_evidence", "request_review"]
    limitations: list[str] = Field(min_length=1, max_length=6)
