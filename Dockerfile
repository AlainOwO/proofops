FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
COPY --from=ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 /uv /bin/uv
COPY --from=openpolicyagent/conftest:v0.71.0@sha256:3ec6dad358db08acecda56b7a3184037cd810394a65046fafa4f33c7750141b1 /conftest /usr/local/bin/conftest
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend backend
COPY alembic.ini ./
COPY migrations migrations
COPY config config
COPY contracts contracts
COPY policies policies
COPY fixtures/replays fixtures/replays
COPY fixtures/billing fixtures/billing
COPY fixtures/negative_cases fixtures/negative_cases
COPY demo demo
RUN uv sync --frozen --no-dev && useradd --uid 10001 --create-home proofops && mkdir -p /app/artifacts && chown proofops:proofops /app/artifacts
ENV PATH="/app/.venv/bin:$PATH"
USER proofops
CMD ["uvicorn", "proofops.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
