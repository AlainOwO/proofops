# Owner and interview walkthrough

Allow about ten minutes. Use a running local app at `http://127.0.0.1:5173`; no cloud or model key is needed. This is a demonstration of implemented behavior, not recorded peer usability feedback.

1. State the problem: an engineer needs to connect a proposed ECS cost change to dated evidence and an approved operating contract. The system is advisory and reviews one explicitly mapped service.
2. Run the **valid-resize** replay. Show its synthetic origin, recorded reference time, 2 vCPU / 4 GiB baseline and 1 vCPU / 2 GiB candidate. The synthetic rate card produces an estimated 50% task CPU/memory reduction with unchanged task-hours. Point to excluded charges and passing fixture workload checks.
3. Open the **unsafe-resize** replay. The 1,024 MiB candidate breaches an approved-in-fixture 2,048 MiB floor. `revise_change` wins even though the arithmetic suggests a larger reduction. Neither AI nor operator enthusiasm can override the finding.
4. Open **incomplete-evidence**. A 20-request artifact cannot satisfy a 10,000-correct-request requirement; missing/stale/incompatible sources remain visible. Explain `collect_evidence` and the exact next evidence needed.
5. Prepare a guard draft from the applicable report, inspect its scope and bound, run fixtures and export. Show that the app has no activation button. Run `proofops guards test` to reproduce the deterministic guard; explain separate protected source review.
6. Enter a different candidate commit in the applicability check. The old approval becomes historical. Export and replay the original bundle to show that reproducibility and current applicability are separate questions.
7. Record an operator disposition, then load the FOCUS sample twice. Show one import, negative costs and exact totals. Explain that this public multi-provider sample is not the demo service's bill and not realized savings.
8. Show `docs/results/` and the local workload manifests. Distinguish actual local OOM/recovery and three comparison pairs from synthetic AWS review evidence. Present provider-policy cells as unrun; do not invent cheap/strong quality or pricing.

## Questions the owner should be able to answer

- **Why not ask an LLM to approve the resize?** Arithmetic, scope and known policy violations have deterministic oracles. Prose can be plausible but causally wrong; explanation validation is not an approval authority.
- **Why PostgreSQL instead of only files?** Concurrent leases, idempotency and budget reservations need transactional state; files remain useful for portable immutable exports.
- **Why only one guard family?** A typed fixed template makes scope, exceptions and fixture coverage inspectable. Arbitrary generated Rego would broaden both trust and verification requirements.
- **Why not average p95?** A percentile summarizes a distribution. Averaging per-run percentiles is not the percentile of combined requests and can hide a bad run or request class.
- **What happens after a timeout?** Unknown provider charges remain pending; the worker does not assume zero cost and retry indefinitely.
- **What does a hash prove?** Exact byte identity. It does not prove that uploaded measurements are truthful or that an old observation applies now.
- **What would change for a team?** Add authenticated roles, approval separation, protected CI/workflows, secure secret storage, retention and account isolation. None is implied by loopback binding.
- **What was actually measured?** Local test/adapter contracts, deterministic synthetic evaluation and local Docker workload behavior. Live AWS/provider quality, remote CI and uncoached human use are still unrun.

## Glossary

**Contract:** versioned requirements and applicability. **Coverage:** whether supported evidence can answer the question. **Origin:** how evidence was obtained. **Replay:** deterministic reproduction at a recorded time. **Task-hours:** billable running-task time. **Guard:** scoped deterministic constraint. **Lease:** expiring worker ownership. **Reservation:** money set aside before dispatch. **Uncertain charge:** possibly billed attempt awaiting reconciliation. **Oracle:** independently justified expected result. **p95:** latency at or below which 95% of the sampled requests fall. **Abstention:** an explicit request for evidence or a coverage result. **Semantic correctness:** whether the meaning follows from evidence, beyond JSON validity.
