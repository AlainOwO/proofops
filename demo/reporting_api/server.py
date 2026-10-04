"""Independent integer-cent workload; pressure requires an isolated limited container."""

import hmac
import os
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

_durations: deque[float] = deque(maxlen=50_000)
_completed = 0
_pressure: bytearray | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pressure
    if os.getenv("PROOFOPS_ENABLE_PRESSURE") == "I_UNDERSTAND_ISOLATED_CONTAINER":
        limit_path = Path("/sys/fs/cgroup/memory.max")
        if not limit_path.is_file() or not limit_path.read_text().strip().isdigit():
            raise RuntimeError("Pressure requires an enforced cgroup v2 memory limit")
        amount = int(os.getenv("PRESSURE_MIB", "80"))
        if not 1 <= amount <= 256:
            raise RuntimeError("Pressure allocation must be bounded to 1–256 MiB")
        _pressure = bytearray(b"x") * (amount * 1024 * 1024)
    yield
    _pressure = None


app = FastAPI(title="ProofOps isolated reporting workload", lifespan=lifespan)


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(min_length=1, max_length=80)
    amount_cents: Annotated[int, Field(strict=True, ge=-1_000_000_000, le=1_000_000_000)]


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=160)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    items: list[Item] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("item IDs must be unique within a report")
        return self


@app.middleware("http")
async def bounded_request(request: Request, call_next):
    if request.method == "POST":
        total = 0
        chunks = []
        async for chunk in request.stream():
            total += len(chunk)
            if total > 262_144:
                return JSONResponse({"detail": "workload body exceeds 256 KiB"}, status_code=413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
    start = perf_counter()
    response = await call_next(request)
    _durations.append((perf_counter() - start) * 1000)
    return response


@app.get("/healthz")
def health():
    return {"status": "ok", "role": "isolated_workload"}


@app.post("/v1/reports/summary")
def summarize(report: ReportRequest, authorization: str | None = Header(default=None)):
    global _completed
    token = os.getenv("TEST_API_TOKEN", "")
    if token and not hmac.compare_digest(authorization or "", "Bearer " + token):
        raise HTTPException(401, "workload token required")
    result = sum(item.amount_cents for item in report.items)
    _completed += 1
    return {
        "request_id": report.request_id,
        "currency": report.currency,
        "item_count": len(report.items),
        "total_cents": result,
    }


@app.get("/metrics")
def metrics():
    ordered = sorted(_durations)
    return {
        "completed_reports": _completed,
        "sample_count": len(ordered),
        "p95_handler_ms": ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)]
        if ordered
        else None,
        "population": "single_process_handler",
        "note": "k6 client latency is the workload contract measurement",
    }


if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("WORKLOAD_HOST", "127.0.0.1"), port=8080, access_log=False)
