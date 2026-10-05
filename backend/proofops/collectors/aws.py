from datetime import timedelta
from time import monotonic, sleep
from typing import Any, Literal

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import Field

from proofops.config import Settings
from proofops.domain.common import digest, utcnow
from proofops.domain.schemas import EvidenceRecord, Record, Scope
from proofops.storage.bundles import redact_text


class CallLimit(RuntimeError):
    pass


class CollectionSource(Record):
    source: str
    status: Literal["complete", "pending", "denied", "failed", "not_configured"]
    data: dict[str, Any] = Field(default_factory=dict)
    request_metadata: list[dict] = Field(default_factory=list)
    note: str = ""


class AWSCollector:
    def __init__(
        self,
        clients: dict,
        *,
        max_calls: int = 12,
        deadline_seconds: float = 20,
        lookback_seconds: int = 3600,
        max_pages: int = 2,
        log_group: str = "",
        sleeper=sleep,
    ):
        if (
            not 1 <= max_calls <= 30
            or not 60 <= lookback_seconds <= 86400
            or not 1 <= max_pages <= 3
        ):
            raise ValueError("collector limits are outside supported bounds")
        self.clients, self.max_calls, self.deadline_seconds = clients, max_calls, deadline_seconds
        self.lookback, self.max_pages, self.log_group, self.sleeper = (
            lookback_seconds,
            max_pages,
            log_group,
            sleeper,
        )
        self.calls, self.deadline = 0, 0.0
        self.request_metadata: list[dict] = []

    @classmethod
    def from_settings(cls, settings: Settings):
        if not settings.aws_account_id or not settings.aws_cluster or not settings.aws_service:
            raise ValueError("explicit AWS account, cluster and service configuration is required")
        session = boto3.Session(
            profile_name=settings.aws_profile or None, region_name=settings.aws_region
        )
        config = Config(
            connect_timeout=3, read_timeout=5, retries={"max_attempts": 0, "mode": "standard"}
        )
        clients = {
            name: session.client(name, config=config)
            for name in ("sts", "ecs", "cloudwatch", "logs")
        }
        return cls(
            clients,
            max_calls=settings.aws_max_calls,
            lookback_seconds=settings.aws_lookback_seconds,
            log_group=settings.aws_log_group,
        )

    def call(self, service: str, method: str, **kwargs):
        if self.calls >= self.max_calls or monotonic() >= self.deadline:
            raise CallLimit("collector call/deadline budget exhausted")
        self.calls += 1
        try:
            response = getattr(self.clients[service], method)(**kwargs)
        except ClientError as exc:
            metadata = exc.response.get("ResponseMetadata", {})
            self.request_metadata.append(
                {
                    "service": service,
                    "method": method,
                    **{
                        key: metadata[key]
                        for key in ("RequestId", "HTTPStatusCode", "RetryAttempts")
                        if key in metadata
                    },
                }
            )
            raise
        metadata = response.get("ResponseMetadata", {})
        self.request_metadata.append(
            {
                "service": service,
                "method": method,
                **{
                    key: metadata[key]
                    for key in ("RequestId", "HTTPStatusCode", "RetryAttempts")
                    if key in metadata
                },
            }
        )
        return response

    def attempt(self, source: str, function) -> CollectionSource:
        start = len(self.request_metadata)
        try:
            result = function()
            result.request_metadata = self.request_metadata[start:]
            return result
        except CallLimit:
            return CollectionSource(
                source=source,
                status="pending",
                note="Collection stopped at its configured call/time bound.",
                request_metadata=self.request_metadata[start:],
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            denied = code in {
                "AccessDenied",
                "AccessDeniedException",
                "UnauthorizedOperation",
                "UnrecognizedClientException",
            }
            return CollectionSource(
                source=source,
                status="denied" if denied else "failed",
                note="AWS access denied."
                if denied
                else "AWS source failed; provider error body omitted.",
                request_metadata=self.request_metadata[start:],
            )
        except (BotoCoreError, ValueError, KeyError, TypeError):
            return CollectionSource(
                source=source,
                status="failed",
                note="AWS source response was unavailable or incompatible.",
                request_metadata=self.request_metadata[start:],
            )

    def ecs_source(self, scope: Scope) -> CollectionSource:
        response = self.call(
            "ecs", "describe_services", cluster=scope.cluster, services=[scope.service]
        )
        services = response.get("services", [])
        if response.get("failures") or len(services) != 1:
            raise ValueError("service configuration unavailable")
        service = services[0]
        prefix = f"arn:aws:ecs:{scope.region}:{scope.account_id}:"
        cluster_name = scope.cluster.rsplit("/", 1)[-1]
        if (
            service.get("serviceArn") != prefix + f"service/{cluster_name}/{scope.service}"
            or service.get("clusterArn") != prefix + f"cluster/{cluster_name}"
            or service.get("serviceName") != scope.service
        ):
            raise ValueError("service identity mismatch")
        task_arn = service["taskDefinition"]
        if not task_arn.startswith(prefix + "task-definition/"):
            raise ValueError("task definition identity mismatch")
        task = self.call("ecs", "describe_task_definition", taskDefinition=task_arn)[
            "taskDefinition"
        ]
        if task.get("taskDefinitionArn") != task_arn:
            raise ValueError("task definition revision mismatch")
        images = [container.get("image", "") for container in task.get("containerDefinitions", [])]
        image = images[0].split("@")[-1] if len(images) == 1 and "@sha256:" in images[0] else None
        task_arns = []
        token = None
        task_pages_complete = True
        for page in range(self.max_pages):
            kwargs = {
                "cluster": scope.cluster,
                "serviceName": scope.service,
                "desiredStatus": "RUNNING",
                "maxResults": 10,
            }
            if token:
                kwargs["nextToken"] = token
            tasks = self.call("ecs", "list_tasks", **kwargs)
            returned_arns = tasks.get("taskArns", [])
            task_arns.extend(returned_arns[:10])
            if len(returned_arns) > 10:
                task_pages_complete = False
            token = tasks.get("nextToken")
            if not token:
                break
            if page == self.max_pages - 1:
                task_pages_complete = False
        if any(not arn.startswith(prefix + "task/") for arn in task_arns):
            raise ValueError("task population crosses the configured account or region")
        tasks = (
            self.call("ecs", "describe_tasks", cluster=scope.cluster, tasks=task_arns)
            if task_arns
            else {"tasks": []}
        )
        described = tasks.get("tasks", [])
        population_complete = (
            task_pages_complete
            and not tasks.get("failures")
            and {item.get("taskArn") for item in described} == set(task_arns)
            and all(
                item.get("taskDefinitionArn") == task_arn
                and item.get("clusterArn") == prefix + f"cluster/{cluster_name}"
                for item in described
            )
        )
        platform = task.get("runtimePlatform", {})
        return CollectionSource(
            source="aws_ecs",
            status="complete" if population_complete else "pending",
            data={
                "service_arn": service["serviceArn"],
                "task_definition_arn": task_arn,
                "cpu_units": int(task["cpu"]),
                "memory_mib": int(task["memory"]),
                "image_digest": image,
                "architecture": platform.get("cpuArchitecture"),
                "os": platform.get("operatingSystemFamily"),
                "requires_fargate": "FARGATE" in task.get("requiresCompatibilities", []),
                "running_count": service.get("runningCount"),
                "desired_count": service.get("desiredCount"),
                "task_pages_complete": task_pages_complete,
                "task_population_complete": population_complete,
                "tasks": [
                    {
                        key: item.get(key)
                        for key in ("taskArn", "lastStatus", "desiredStatus", "taskDefinitionArn")
                    }
                    for item in tasks.get("tasks", [])[:30]
                ],
            },
            note="Task configuration is baseline evidence only when its exact ARN/allocation/image match the imported plan. Service/task averages do not establish application performance.",
        )

    def metric_source(self, scope: Scope, start, end) -> CollectionSource:
        queries = []
        for identity, metric in (("cpu", "CPUUtilization"), ("memory", "MemoryUtilization")):
            queries.append(
                {
                    "Id": identity,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/ECS",
                            "MetricName": metric,
                            "Dimensions": [
                                {"Name": "ClusterName", "Value": scope.cluster},
                                {"Name": "ServiceName", "Value": scope.service},
                            ],
                        },
                        "Period": 60,
                        "Stat": "Average",
                        "Unit": "Percent",
                    },
                    "ReturnData": True,
                }
            )
        results = []
        token = None
        for _ in range(self.max_pages):
            kwargs = {
                "MetricDataQueries": queries,
                "StartTime": start,
                "EndTime": end,
                "MaxDatapoints": 1440,
                "ScanBy": "TimestampAscending",
            }
            if token:
                kwargs["NextToken"] = token
            response = self.call("cloudwatch", "get_metric_data", **kwargs)
            for item in response.get("MetricDataResults", []):
                results.append(
                    {
                        "id": item.get("Id"),
                        "status": item.get("StatusCode"),
                        "timestamps": [
                            value.isoformat() for value in item.get("Timestamps", [])[:1440]
                        ],
                        "values": item.get("Values", [])[:1440],
                    }
                )
            token = response.get("NextToken")
            if not token:
                break
        complete = not token and all(item["status"] == "Complete" for item in results)
        return CollectionSource(
            source="aws_cloudwatch",
            status="complete" if complete else "pending",
            data={
                "metrics": results,
                "units": "percent",
                "population": "service_average",
                "sample_count": sum(len(item["values"]) for item in results),
            },
            note="An empty successful query is not zero utilization or zero errors; these averages are context, not an application latency/correctness measurement.",
        )

    def log_source(self, start, end) -> CollectionSource:
        if not self.log_group:
            return CollectionSource(
                source="aws_logs",
                status="not_configured",
                note="No explicitly configured log group.",
            )
        query = self.call(
            "logs",
            "start_query",
            logGroupName=self.log_group,
            startTime=int(start.timestamp()),
            endTime=int(end.timestamp()),
            queryString="fields @timestamp, @message | sort @timestamp desc | limit 20",
            limit=20,
        )
        query_id = query["queryId"]
        while self.calls < self.max_calls - 1 and monotonic() < self.deadline - 1:
            response = self.call("logs", "get_query_results", queryId=query_id)
            state = response.get("status", "Unknown")
            if state not in {"Scheduled", "Running"}:
                rows = [
                    {
                        item["field"]: redact_text(item.get("value", ""))
                        for item in row
                        if item.get("field") in {"@timestamp", "@message"}
                    }
                    for row in response.get("results", [])[:20]
                ]
                return CollectionSource(
                    source="aws_logs",
                    status="complete" if state == "Complete" else "failed",
                    data={
                        "query_id": query_id,
                        "query_status": state,
                        "rows": rows,
                        "statistics": response.get("statistics", {}),
                    },
                    note="Messages are redacted, bounded untrusted data. Query scan charges may apply.",
                )
            self.sleeper(0.1)
        if self.calls < self.max_calls and monotonic() < self.deadline:
            self.call("logs", "stop_query", queryId=query_id)
        return CollectionSource(
            source="aws_logs",
            status="pending",
            data={"query_id": query_id, "query_status": "deadline_or_call_limit"},
            note="Incomplete query stopped at the configured bound; no completed result is claimed.",
        )

    def collect(self, scope: Scope) -> dict:
        self.calls = 0
        self.request_metadata = []
        self.deadline = monotonic() + self.deadline_seconds
        if any(
            client.meta.region_name != scope.region
            for name, client in self.clients.items()
            if name != "sts"
        ):
            raise ValueError("collector clients do not match the configured region")
        end = utcnow()
        start = end - timedelta(seconds=self.lookback)
        identity = self.call("sts", "get_caller_identity")
        if identity.get("Account") != scope.account_id:
            raise ValueError("STS caller account differs from configured review scope")
        sources = [
            self.attempt("aws_ecs", lambda: self.ecs_source(scope)),
            self.attempt("aws_cloudwatch", lambda: self.metric_source(scope, start, end)),
            self.attempt("aws_logs", lambda: self.log_source(start, end)),
        ]
        return {
            "schema_version": 1,
            "mode": "live",
            "origin": "aws_observation",
            "scope": scope.model_dump(mode="json"),
            "observed_start": start.isoformat(),
            "observed_end": end.isoformat(),
            "collected_at": utcnow().isoformat(),
            "calls": self.calls,
            "limits": {
                "max_calls": self.max_calls,
                "lookback_seconds": self.lookback,
                "deadline_seconds": self.deadline_seconds,
                "max_pages": self.max_pages,
            },
            "identity_request_metadata": self.request_metadata[:1],
            "sources": [source.model_dump(mode="json") for source in sources],
        }


def task_evidence(collection: dict) -> EvidenceRecord:
    source = next(item for item in collection["sources"] if item["source"] == "aws_ecs")
    data = source.get("data", {})
    return EvidenceRecord(
        evidence_id="ecs-" + digest(source)[:24],
        kind="task_configuration",
        source="aws_ecs",
        scope=Scope.model_validate(collection["scope"]),
        resource_revision=data.get("task_definition_arn", "unavailable"),
        observed_start=collection["observed_start"],
        observed_end=collection["observed_end"],
        collected_at=collection["collected_at"],
        collection_status=source["status"],
        units="records",
        population="mapped_service",
        sample_count=1 if source["status"] == "complete" else None,
        content_hash=digest(source),
        origin=collection["origin"],
        redaction_state="allowlisted",
        metadata={
            key: data.get(key)
            for key in (
                "cpu_units",
                "memory_mib",
                "image_digest",
                "task_definition_arn",
                "architecture",
                "os",
                "requires_fargate",
                "task_population_complete",
            )
        },
    )


class ReplayCollector:
    def __init__(self, recorded: dict):
        self.recorded = recorded

    def collect(self, scope: Scope) -> dict:
        if Scope.model_validate(self.recorded["scope"]) != scope:
            raise ValueError("recorded collector scope mismatch")
        for source in self.recorded["sources"]:
            CollectionSource.model_validate(source)
        return {**self.recorded, "mode": "replay"}
