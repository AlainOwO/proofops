# Evaluation and economics

The frozen corpus is `manifest.json`: 60 original synthetic cases from 20 scenario groups, three variants each. Eight groups are development, four routing calibration and eight held-out. A group never crosses splits. `evaluator_only/labels.json` contains independently authored outcomes, finding predicates, guard specifications and rationales. The generator does not call the engine to produce expected labels. One documented vocabulary correction occurred before the first run; the manifest records it. Do not regenerate or tune against held-out results and keep calling them untouched.

The current corpus checks one guard family and variations on explicit constraints, not general incident diagnosis. The original research's eight worked examples remain development material. No RCAEval index, evaluator label, revealing file path or case ID is submitted to a model. API and worker images do not include this directory. Only explicit evaluation/test commands may read labels.

## Reproduce the local run

```sh
.venv/bin/proofops evaluate --manifest evaluation/manifest.json --mode replay --output artifacts/evaluation
```

This writes `summary.json`, `deterministic.json`, `contexts.json` and `results.jsonl`. The three provider policies are marked **unrun** when replay is requested or live prerequisites are absent. Null cost/latency/quality means unmeasured; it does not mean free, fast or correct. `template` runs without keys or PostgreSQL. The standard CLI returns failure if any deterministic case disagrees with its oracle.

Each case schedules an explanation task and a guard/applicability task for template, cheap-only, strong-only and routed policies. Records include group/split, immutable input hash, expected label, actual output, prompt/schema/model/price metadata, route, provider attempts, usage, latency and known/pending cost. Provider failure and deterministic fallback remain visible in the record. Split-specific summaries preserve held-out denominators.

The local template run has 60/60 deterministic outcomes/predicates, 57 structured explanations plus three correct out-of-scope abstentions, and 54 applicable draft specifications plus six correctly inapplicable guard cases. It therefore has 111 structured accepted outputs across 120 scheduled template tasks. The other 360 scheduled tasks are unrun. These counts are regenerated from saved results in the PDF tables, not used as dashboard constants.

## What each score means

Deterministic correctness checks expected outcome, required findings and specified cost predicates. Unsafe false negatives, healthy false positives and evidence abstentions in the summary refer to the engine's decision; they do not measure the safety of generated prose. Mechanical validity checks schema, exact references and numeric facts for structured explanations. Semantic correctness asks whether the explanation's meaning is supported. A valid citation can accompany an unsupported causal claim; the negative-control tests deliberately prove that distinction.

Known deterministic templates are scored against a narrow authored rubric. New model prose without an independent annotation receives `correct: null`. A stronger model's agreement or self-confidence never creates a truth label. Guard scoring uses the exact independently supplied scope, memory floor, references and draft state; inapplicable cases are counted separately from actual drafts.

Cost per attempted task includes failed calls, retries and escalation. Cost per correct explanation divides the total explanation-task cost, including failures, by independently correct explanations. Any unresolved charge keeps totals/cost-per-correct null. A second attempt is not automatically an escalation: changing provider/model is reported separately from a same-model retry. Local evaluator latency includes engine, context/retrieval and routing/SDK work, but has no API queue; persisted UI jobs expose queue timestamps separately.

## Annotate saved outputs without paid reruns

Create an annotation JSON inside application `artifacts/`. Copy the exact `annotation_key` from a saved explanation record; it binds the full output, task and input hash. A reviewer must inspect the relevant evidence and write a Boolean judgment plus a rationale. Do not copy this structural example as a real judgment:

```json
{
  "<annotation_key from the saved record>": {
    "correct": false,
    "reviewer": "<reviewer identifier>",
    "rationale": "<specific claim and evidence supporting the judgment>"
  }
}
```

```sh
.venv/bin/python -m evaluation.rescore --results-dir artifacts/evaluation --annotations artifacts/annotations.json --output artifacts/evaluation-rescored
```

The destination must be new. The command preserves original outputs, usage, costs and timing; it makes no provider call. A judgment cannot leak onto the same prose with different evidence. Tests include deliberately wrong annotations only as scorer controls; they are not claimed as peer review. Live evaluation uses `python -m evaluation.run --mode live` only after IDs, keys, dated prices and explicit positive budgets are configured. No live provider experiment was run for this handoff.

## Context experiment and uncertainty

The runner prepares compact and bounded-flat contexts from the same underlying report evidence. It records byte counts, hashes and omissions. If a representation exceeds the cap, it is excluded, not scored as model failure. Serialization bytes and the research's reference-token counts are not billed API tokens. The current experiment establishes reproducible inputs only; downstream semantic quality and token-cost comparison remain unrun.

Three variants per group are correlated. Descriptive 60-case accuracy cannot imply 60 independent incident trials or broad quality parity. Even zero errors in 30 independent accepted cases has a one-sided 95% upper error bound near 9.5%; 300 such cases lowers it to about 1%. Those are illustrative statistical bounds, not confidence intervals for this synthetic corpus. A future study needs additional independent scenarios, frozen development/calibration decisions, independent reviewers and sufficient accepted held-out coverage, including cheap-model failures.

Sources: [RouteLLM](https://arxiv.org/abs/2406.18665), [FrugalGPT](https://arxiv.org/abs/2305.05176), [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).
