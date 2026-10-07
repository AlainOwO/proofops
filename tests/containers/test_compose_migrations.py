"""Real Compose startup and API-only rebuilds, with private, retained test volumes."""

import json
import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from proofops.config import APP_ROOT
from proofops.storage.database import SCHEMA_REVISION

PREVIOUS_REVISION = "f6a91d2e83b4"
HOST = "migration-check.example"

DATABASE_STATE = """
import json
from alembic.config import Config
from alembic.script import ScriptDirectory
from proofops.config import APP_ROOT
from proofops.storage.database import SCHEMA_REVISION, make_engine
from sqlalchemy import text
config = Config(str(APP_ROOT / 'alembic.ini'))
config.set_main_option('script_location', str(APP_ROOT / 'migrations'))
with make_engine().connect() as connection:
    revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    database, role = connection.execute(text('SELECT current_database(), current_user')).one()
    cache = connection.execute(text("SELECT to_regclass('public.tool_observation_cache')")).scalar_one()
    sentinel = connection.execute(text("SELECT data FROM contracts WHERE id = 'migration-sentinel'")).scalar_one_or_none()
print(json.dumps(dict(revision=revision, expected=SCHEMA_REVISION,
                     heads=ScriptDirectory.from_config(config).get_heads(),
                     database=database, role=role, cache=cache, sentinel=sentinel)))
"""

READINESS = """
import json
import os
import httpx
try:
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=3,
                      headers={'Host': os.environ['ALLOWED_HOSTS'].split(',')[0]}) as client:
        if os.getenv('PROOFOPS_PUBLIC_DEMO', 'false') != 'true':
            challenge = client.get('/api/v1/auth/login')
            login = client.post('/api/v1/auth/login',
                                json={'username': os.environ['PROOFOPS_ADMIN_USERNAME'],
                                      'password': os.environ['PROOFOPS_ADMIN_PASSWORD']},
                                headers={'Origin': os.environ['CORS_ORIGINS'],
                                         'X-CSRF-Token': challenge.json()['csrf_token']})
            assert login.status_code == 200, 'Synthetic admin must authenticate normally'
        response = client.get('/readyz')
        print(json.dumps({'status': response.status_code, 'body': response.json()}))
except httpx.RequestError:
    print(json.dumps({'status': 0}))
"""


class ComposeStack:
    def __init__(self, filename, starting_schema):
        self.project = f"proofops-migration-{uuid4().hex[:12]}"
        self.directory = APP_ROOT / "artifacts/compose-migrations" / self.project
        self.directory.mkdir(parents=True, mode=0o700)
        self.private = self.directory / "private"
        self.private.mkdir(mode=0o700)
        self.filename = filename
        self.hosted = filename == "compose.hosted.yaml"
        self.credentials = {
            name: secrets.token_urlsafe(48)
            for name in (
                "POSTGRES_PASSWORD",
                "PROOFOPS_OWNER_PASSWORD",
                "PROOFOPS_RUNTIME_PASSWORD",
                "SECRET_KEY",
                "PROOFOPS_ADMIN_PASSWORD",
            )
        }
        values = {
            **self.credentials,
            "HOSTED_DOMAIN": HOST,
            "ACME_EMAIL": "operator@example.com",
            "ALLOWED_HOSTS": "127.0.0.1,localhost",
            "CORS_ORIGINS": "http://127.0.0.1:5173",
            "PROOFOPS_ADMIN_USERNAME": "migration-check-admin",
            "SESSION_COOKIE_SECURE": "false",
            "AI_MODE": "off",
            "AWS_EC2_METADATA_DISABLED": "true",
        }
        self.env_file = self.private / "test.env"
        self.env_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
        self.env_file.chmod(0o600)
        # Explicit test interpolation values take precedence over the caller's
        # environment. No root .env or hosted secret file is loaded.
        self.environment = {
            key: value for key, value in os.environ.items() if not key.startswith("COMPOSE_")
        }
        self.environment.update(values)
        self.override = self.private / "isolation.yaml"
        self.override.write_text(
            "services:\n  db:\n    ports: !reset []\n  api:\n    ports: !reset []\n"
            "    environment:\n"
            "      PROOFOPS_ADMIN_USERNAME: ${PROOFOPS_ADMIN_USERNAME}\n"
            "      PROOFOPS_ADMIN_PASSWORD: ${PROOFOPS_ADMIN_PASSWORD}\n"
            + (
                ""
                if self.hosted
                else f"    env_file: !override [{json.dumps(str(self.env_file))}]\n"
                f"  worker:\n    env_file: !override [{json.dumps(str(self.env_file))}]\n"
            )
        )
        docker = shutil.which("docker")
        assert docker is not None, "Docker and Compose 2.24.4+ are required"
        self.docker = docker
        self.prefix = [
            "compose",
            "--project-name",
            self.project,
            "--env-file",
            str(self.env_file),
            "-f",
            str(APP_ROOT / filename),
            "-f",
            str(self.override),
        ]
        self.evidence = {"project": self.project, "compose": filename, "initial": starting_schema}

    def run(self, *arguments, timeout=120, check=True):
        result = subprocess.run(  # noqa: S603
            [self.docker, *arguments],
            cwd=APP_ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        for secret in self.credentials.values():
            result.stdout = result.stdout.replace(secret, "[redacted]")
            result.stderr = result.stderr.replace(secret, "[redacted]")
        with (self.directory / "commands.log").open("a") as log:
            log.write(f"docker {' '.join(arguments)}\n{result.stdout}{result.stderr}\n")
        if check and result.returncode:
            pytest.fail(
                f"Docker command failed ({result.returncode}); project={self.project}, "
                f"logs={self.directory / 'commands.log'}\n{result.stdout[-4000:]}"
                f"{result.stderr[-4000:]}"
            )
        return result

    def compose(self, *arguments, **kwargs):
        return self.run(*self.prefix, *arguments, **kwargs)

    def api_python(self, source):
        return self.compose("exec", "-T", "api", "python", "-c", source)

    def prepare(self):
        assert (
            self.run(
                "ps", "-aq", "--filter", f"label=com.docker.compose.project={self.project}"
            ).stdout.strip()
            == ""
        ), "Refusing to reuse an existing Compose project"
        assert (
            self.run(
                "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={self.project}"
            ).stdout.strip()
            == ""
        ), "Refusing to reuse an existing volume"
        model = json.loads(self.compose("--profile", "*", "config", "--format", "json").stdout)
        services = model["services"]
        self.image = services["api"]["image"]
        assert self.image.startswith(self.project + "-"), "Test backend image must be isolated"
        assert services["migrate"]["image"] == self.image, "API and migrate must share one image"
        assert services["worker"]["image"] == self.image, "Workers must share the schema image"
        # Deliberately build API only: this must also supply the migration image.
        self.compose("build", "db", "api", timeout=900)

    def use_previous_image(self):
        current = f"{self.project}-current"
        self.run("image", "tag", self.image, current)
        config = Config(str(APP_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(APP_ROOT / "migrations"))
        script = ScriptDirectory.from_config(config)
        remove = [
            Path(revision.path).name
            for revision in script.iterate_revisions("heads", PREVIOUS_REVISION)
        ]
        assert remove, "The fixture must exercise at least one real schema migration"
        # Manufacture the earlier image only in this private build context.
        # Its actual Alembic chain and readiness contract both end at f6a91d2e83b4.
        previous_code = (
            "from pathlib import Path; "
            f"files={remove!r}; "
            "[(Path('/app/migrations/versions') / name).unlink() for name in files]; "
            "path=Path('/app/backend/proofops/storage/database.py'); "
            f"path.write_text(path.read_text().replace({SCHEMA_REVISION!r}, {PREVIOUS_REVISION!r}))"
        )
        dockerfile = self.private / "Dockerfile.previous"
        dockerfile.write_text(
            f"FROM {current}\nUSER root\n"
            f"RUN {json.dumps(['python', '-c', previous_code])}\nUSER proofops\n"
        )
        self.run(
            "build",
            "--file",
            str(dockerfile),
            "--tag",
            self.image,
            str(self.private),
            timeout=120,
        )

    def start_and_verify(self, revision, *, build=False):
        self.compose(
            "up",
            "--detach",
            "--build" if build else "--no-build",
            "--pull",
            "never",
            "api",
            timeout=900 if build else 120,
        )
        ids = {
            service: self.compose("ps", "--all", "--quiet", service).stdout.strip()
            for service in ("api", "migrate", "db")
        }
        assert all(ids.values()), "Compose must create DB, migration and API services"
        states = {
            service: json.loads(
                self.run(
                    "inspect",
                    "--format",
                    '{"image":{{json .Image}},"status":{{json .State.Status}},'
                    '"exit":{{.State.ExitCode}}}',
                    container_id,
                ).stdout
            )
            for service, container_id in ids.items()
        }
        assert states["migrate"]["status"] == "exited"
        assert states["migrate"]["exit"] == 0, "The migration service must finish successfully"
        assert states["api"]["image"] == states["migrate"]["image"]
        deadline = time.monotonic() + 45
        response = None
        while time.monotonic() < deadline:
            result = self.compose("exec", "-T", "api", "python", "-c", READINESS, check=False)
            if result.returncode == 0:
                response = json.loads(result.stdout)
                if response["status"] == 200:
                    break
            time.sleep(0.3)
        assert response == {"status": 200, "body": {"status": "ready", "ai_required": False}}
        database = json.loads(self.api_python(DATABASE_STATE).stdout)
        assert database["revision"] == database["expected"] == revision
        assert database["heads"] == [revision]
        assert database["database"] == "proofops"
        assert database["role"] == ("proofops_runtime" if self.hosted else "proofops")
        assert bool(database["cache"]) is (revision != PREVIOUS_REVISION)
        self.evidence.setdefault("starts", []).append(
            {"containers": ids, "states": states, "database": database, "readyz": response}
        )
        return ids, database

    def finish(self):
        self.compose("logs", "--no-color", check=False)
        before = self.run(
            "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={self.project}"
        ).stdout.splitlines()
        # The unique project owns only test containers/networks. Named volumes
        # are deliberately retained, including on failures, for diagnosis.
        self.compose("down", "--timeout", "10")
        retained = self.run(
            "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={self.project}"
        ).stdout.splitlines()
        self.evidence["retained_volumes"] = retained
        (self.directory / "result.json").write_text(json.dumps(self.evidence, indent=2) + "\n")
        assert retained == before, "Test database volumes must remain available after shutdown"


@pytest.mark.parametrize("filename", ["compose.yaml", "compose.hosted.yaml"])
@pytest.mark.parametrize("starting_schema", ["fresh", PREVIOUS_REVISION])
def test_compose_migration_success_means_api_database_is_at_head(filename, starting_schema):
    stack = ComposeStack(filename, starting_schema)
    try:
        stack.prepare()
        previous_ids = None
        if starting_schema == PREVIOUS_REVISION:
            stack.use_previous_image()
            previous_ids, _ = stack.start_and_verify(PREVIOUS_REVISION)
            stack.api_python(
                """
from sqlalchemy import text
from proofops.storage.database import make_engine
with make_engine().begin() as connection:
    connection.execute(text('''
        INSERT INTO contracts (id, scope, data, created_at)
        VALUES (:id, :scope, CAST(:data AS jsonb), CURRENT_TIMESTAMP)
    '''), dict(id='migration-sentinel', scope='preserve-existing-data', data='{"preserved":true}'))
"""
            )
            # Reproduce the incident: the previous migrate has already exited
            # zero and only API is rebuilt, then ordinary Compose up is run.
            stack.compose("build", "api", timeout=900)
        # Fresh deployments also exercise the usual up --build path, which
        # builds several services sharing the backend tag in one invocation.
        current_ids, database = stack.start_and_verify(
            SCHEMA_REVISION, build=starting_schema == "fresh"
        )
        if previous_ids:
            assert current_ids["db"] == previous_ids["db"], "Upgrade must use the same database"
            assert current_ids["migrate"] != previous_ids["migrate"], (
                "Rebuild must rerun migrations"
            )
            assert current_ids["api"] != previous_ids["api"]
            assert database["sentinel"] == {"preserved": True}, "Existing data must survive"
    finally:
        stack.finish()
