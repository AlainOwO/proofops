# CI trust and reproduction

The committed workflow performs backend/evaluation checks, frontend build/browser tests and a trusted-policy recurrence demonstration without cloud/model credentials. It generates ephemeral local database/session secrets and synthetic browser credentials during setup; no fixed passwords are embedded in the workflow. Action commits were resolved from official release endpoints on 2026-10-05 and recorded in `build_tool_sources.json`. The workflow uses read-only repository permissions and does not use `pull_request_target`.

The browser job signs in, runs all e2e tests, reseeds the three results and runs the existing screenshot script. Network traces/videos and persisted browser cookie files are disabled. Artifact uploads use explicit report/screenshot directories, excluding `.env` and `artifacts/private/`. Local equivalents are verified; editing this workflow does not claim a remote Actions run or deployment.

The trusted-policy job checks out the base revision in `trusted/` and candidate fixture data in `incoming/`. It executes the base engine and policy code. `scripts/ci_review.py` copies only bounded allowlisted JSON files, rejects links and evaluator paths, and requires the candidate identity mapping to match the trusted mapping. The candidate cannot supply its own weakened policy/template. The known-bad synthetic fixture must still produce `revise_change`; the script treats that expected rejection as a passing regression test.

The artifact contains exact input and trusted revision hashes. The job summary identifies the code revision separately from the synthetic infrastructure candidate commit. It does not claim that fixture evidence validates arbitrary PR code or deployed resources.

Local reproduction:

```sh
PROOFOPS_CANDIDATE_REVISION=$(git rev-parse HEAD)
.venv/bin/python scripts/ci_review.py --bundle fixtures/replays/unsafe-resize --source-revision "$PROOFOPS_CANDIDATE_REVISION"
```

PowerShell:

```powershell
$proofopsCandidateRevision = git rev-parse HEAD
.venv\Scripts\python.exe scripts/ci_review.py --bundle fixtures/replays/unsafe-resize --source-revision $proofopsCandidateRevision
```

The script also records its own actual trusted Git revision. The normal CLI commands in the README reproduce the engine without a CI account.

A required production check additionally needs a protected trusted workflow definition, protected policy/mapping/template review and branch/environment enforcement. Protect `.github/workflows/` too: an editable PR workflow is not an immutable enforcement authority. A team can use repository rulesets/required workflows and code owners where available. Generating a real Terraform plan belongs in the team's trusted workflow, with secret handling and exact commit/image/evidence binding. Those repository and deployment settings have not been configured here, and no remote CI run is claimed.
