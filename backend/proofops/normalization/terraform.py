import re
from typing import Any

from proofops.domain.common import digest, strict_json
from proofops.domain.schemas import ChangeSet, ServiceMap, TaskConfiguration

# Linux Fargate pairs supported by this implementation. Larger 8/16-vCPU platform
# variants are deliberately outside v1. Source/version is included in exports.
CPU_MEMORY_V1 = {
    256: {512, 1024, 2048},
    512: set(range(1024, 4097, 1024)),
    1024: set(range(2048, 8193, 1024)),
    2048: set(range(4096, 16385, 1024)),
    4096: set(range(8192, 30721, 1024)),
}
CPU_MEMORY_SOURCE = (
    "https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-cpu-memory-error.html"
)


def metadata_paths(value: Any, prefix: str = "") -> list[str]:
    if value is True:
        return [prefix or "*"]
    if isinstance(value, dict):
        return [
            path
            for key, child in value.items()
            for path in metadata_paths(child, f"{prefix}.{key}".strip("."))
        ]
    if isinstance(value, list):
        return [
            path
            for index, child in enumerate(value)
            for path in metadata_paths(child, f"{prefix}[{index}]")
        ]
    if value is False or value is None:
        return []
    raise ValueError(
        "Terraform unknown/sensitive metadata must contain booleans, arrays or objects"
    )


def blocked(paths: list[str], key: str) -> bool:
    return any(
        path == "*" or path == key or path.startswith(key + ".") or path.startswith(key + "[")
        for path in paths
    )


def allocation(value: Any) -> int | None:
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,6}", value):
        return int(value)
    # Terraform provider task attributes are strings. Exact positive JSON integers
    # are also supported; floats, booleans, units and expressions are not.
    if type(value) is int and 0 < value <= 1_000_000:
        return value
    return None


def task_config(raw: dict[str, Any] | None, unavailable: list[str]) -> TaskConfiguration | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("task configuration must be an object or null")
    # Provider-computed revision identifiers change on every resize; they are
    # identity references, not workload configuration differences.
    semantic = {
        key: value
        for key, value in raw.items()
        if key not in {"id", "arn", "arn_without_revision", "revision", "tags_all"}
    }
    image = None
    containers = raw.get("container_definitions")
    if not blocked(unavailable, "container_definitions"):
        try:
            parsed = strict_json(containers) if isinstance(containers, str) else containers
            semantic["container_definitions"] = parsed
            if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
                value = parsed[0].get("image", "")
                if isinstance(value, str) and re.search(r"@sha256:[a-f0-9]{64}$", value):
                    image = value.split("@")[-1]
        except (ValueError, TypeError):
            pass
    platform = raw.get("runtime_platform", [])
    platform = platform[0] if isinstance(platform, list) and len(platform) == 1 else platform
    platform = platform if isinstance(platform, dict) else {}
    other = {key: value for key, value in semantic.items() if key not in {"cpu", "memory"}}
    arn = raw.get("arn")
    valid_arn = isinstance(arn, str) and re.fullmatch(
        r"arn:aws:ecs:[a-z0-9-]+:\d{12}:task-definition/[A-Za-z0-9_-]+:\d+", arn
    )
    return TaskConfiguration(
        cpu_units=None if blocked(unavailable, "cpu") else allocation(raw.get("cpu")),
        memory_mib=None if blocked(unavailable, "memory") else allocation(raw.get("memory")),
        os=None
        if blocked(unavailable, "runtime_platform")
        else platform.get("operating_system_family"),
        architecture=None
        if blocked(unavailable, "runtime_platform")
        else platform.get("cpu_architecture"),
        image_digest=image,
        task_definition_arn=arn if valid_arn and not blocked(unavailable, "arn") else None,
        config_hash=digest(semantic),
        non_resize_config_hash=digest(other),
    )


def normalize(plan: dict[str, Any], service_map: ServiceMap, source_hash: str) -> ChangeSet:
    if not isinstance(plan, dict) or not isinstance(plan.get("resource_changes"), list):
        raise ValueError("plan.resource_changes must be an array from terraform show -json")
    if len(plan["resource_changes"]) > 200:
        raise ValueError("plan contains more than 200 resource changes")
    if not all(isinstance(item, dict) for item in plan["resource_changes"]):
        raise ValueError("each resource change must be an object")
    matching = [
        item
        for item in plan["resource_changes"]
        if item.get("address") == service_map.scope.terraform_address
    ]
    if len(matching) > 1:
        raise ValueError("duplicate mapped resource address")
    base: dict[str, Any] = dict(
        source_hash=source_hash, service_map=service_map, shape_version="ecs-fargate-linux-v1"
    )
    if not matching or matching[0].get("type") != "aws_ecs_task_definition":
        return ChangeSet(
            **base,
            address=None,
            actions=[],
            before=None,
            after=None,
            supported=False,
            applicable_resource=False,
            normalization_findings=["UNSUPPORTED_RESOURCE_SHAPE"],
        )
    item = matching[0]
    change = item.get("change")
    if not isinstance(change, dict) or not isinstance(change.get("actions"), list):
        raise ValueError("mapped resource change/actions are required")
    actions = change["actions"]
    if not actions or not all(
        isinstance(action, str) and action in {"create", "update", "delete", "no-op", "read"}
        for action in actions
    ):
        raise ValueError("unrecognized Terraform change action")
    unknown = metadata_paths(change.get("after_unknown", {}))
    after_sensitive = metadata_paths(change.get("after_sensitive", {}))
    before_sensitive = metadata_paths(change.get("before_sensitive", {}))
    before = task_config(change.get("before"), before_sensitive)
    after = task_config(change.get("after"), unknown + after_sensitive)
    findings: list[str] = []
    supported = actions in (["update"], ["no-op"])
    if str(plan.get("format_version", "")) not in {"1.0", "1.1", "1.2"}:
        supported = False
    for raw, config in ((change.get("before"), before), (change.get("after"), after)):
        if not config:
            supported = False
            continue
        if (
            not isinstance(raw, dict)
            or not isinstance(raw.get("requires_compatibilities"), list)
            or "FARGATE" not in raw["requires_compatibilities"]
            or raw.get("network_mode") != "awsvpc"
        ):
            supported = False
        if config.os != "LINUX" or config.architecture != "X86_64":
            supported = False
        if config.cpu_units is None or config.memory_mib is None:
            findings.append("TERRAFORM_VALUE_UNKNOWN")
        elif config.memory_mib not in CPU_MEMORY_V1.get(config.cpu_units, set()):
            supported = False
            findings.append("UNSUPPORTED_FARGATE_COMBINATION")
    if not supported:
        findings.append("UNSUPPORTED_RESOURCE_SHAPE")
    if after_sensitive or before_sensitive:
        findings.append("SENSITIVE_FIELDS_REDACTED")
    if (
        before
        and after
        and before.cpu_units == after.cpu_units
        and before.memory_mib == after.memory_mib
    ):
        findings.append("TASK_ALLOCATION_UNCHANGED")
    return ChangeSet(
        **base,
        address=item["address"],
        actions=actions,
        before=before,
        after=after,
        unknown_paths=unknown,
        sensitive_paths=sorted(set(before_sensitive + after_sensitive)),
        supported=supported,
        applicable_resource=True,
        normalization_findings=sorted(set(findings)),
    )
