export interface SessionInfo {
  username: string | null;
  role: "admin" | "viewer";
  public_demo: boolean;
  csrf_token: string | null;
  expires_at: string | null;
}

export type Outcome =
  | "request_review"
  | "revise_change"
  | "collect_evidence"
  | "out_of_scope";
export type Json =
  | null
  | string
  | number
  | boolean
  | Json[]
  | { [key: string]: Json };
export interface Summary {
  id: string;
  bundle_id: string;
  state: string;
  stage: string;
  mode: string;
  outcome: Outcome | null;
  origin: string | null;
  service: string | null;
  candidate_commit: string | null;
  created_at: string;
  updated_at: string;
  error_code: string | null;
}
export interface Cost {
  currency: string;
  baseline_amount: string | null;
  candidate_amount: string | null;
  projected_difference: string | null;
  projected_reduction_fraction: string | null;
  baseline_task_hours: string | null;
  candidate_task_hours: string | null;
  rate_id: string;
  price_date: string;
  source_url: string;
  region: string;
  architecture: string;
  os: string;
  purchase_option: string;
  origin: string;
  complete: boolean;
  covered: string[];
  excluded: string[];
  assumptions: string[];
  cost_per_correct_request: Record<string, string | null>;
}
export interface TaskConfig {
  cpu_units: number | null;
  memory_mib: number | null;
  image_digest: string | null;
  config_hash: string;
}
export interface Finding {
  code: string;
  severity: string;
  message: string;
  fact_ids: string[];
}
export interface Workload {
  run_id: string;
  role: string;
  valid_evidence: boolean;
  passed: boolean;
  reasons: string[];
  correct: number;
  completed: number;
  offered: number;
  p95_latency_ms: string | null;
  http_failures: number;
  dropped_iterations: number;
  restarts: number;
  origin: string;
  request_classes: Record<
    string,
    { completed: number; correct: number; p95_latency_ms: string | null }
  >;
}
export interface SourceRecord {
  id: string;
  collection: string;
  freshness: string;
  coverage: string;
  origin: string;
  observed_end: string;
  source: string;
}
export interface CoreReport {
  review_id: string;
  outcome: Outcome;
  origin: string;
  mode: string;
  evaluation_reference_time: string;
  trusted_revision_hash: string;
  input_hashes: Record<string, string>;
  next_steps: string[];
  findings: Finding[];
  cost: Cost | null;
  coverage: {
    supported: boolean;
    trusted_contract: boolean;
    guard_applicable: boolean;
    time_basis: string;
    sources: Record<
      string,
      {
        coverage: string;
        records?: SourceRecord[];
        collection?: string;
        freshness?: string;
      }
    >;
  };
  performance: {
    comparable: boolean;
    complete: boolean;
    passed: boolean;
    runs: Workload[];
    aggregation: string;
  };
  facts: {
    fact_id: string;
    value: string | number | boolean | null;
    kind: string;
  }[];
  change: {
    before: TaskConfig | null;
    after: TaskConfig | null;
    service_map: {
      candidate_commit: string;
      base_commit: string;
      repository: string;
      scope: {
        service: string;
        account_id: string;
        region: string;
        cluster: string;
        environment: string;
        terraform_address: string;
      };
    };
  };
}
export interface Explanation {
  status: string;
  source: string;
  reason?: string;
  route_reason?: string;
  summary?: string;
  output: {
    summary: string;
    limitations: string[];
    cited_facts: { fact_id: string; value: Json }[];
  } | null;
  fallback?: Explanation;
  incremental_cost_usd: string;
  attempts: Json[];
}
export interface Draft {
  id: string;
  state: string;
  spec: {
    minimum_task_memory_mib: number;
    incident_id: string;
    approval_reference: string;
  };
  fixture_results: {
    passed?: boolean;
    status?: string;
    fixtures?: { id: string; passed: boolean; actual: string }[];
  };
}
export interface Detail {
  job: Summary;
  report: CoreReport | null;
  explanation: Explanation | null;
  guard_drafts?: Draft[];
  applicability?: {
    candidate_changed: boolean;
    policy_changed: boolean;
    stale_now: boolean;
    historical_snapshot: boolean;
    message: string;
  };
}
export interface Analytics {
  review_counts: Partial<Record<Outcome, number>>;
  review_count: number;
  projected_comparisons: {
    review_id: string;
    outcome: Outcome;
    origin: string;
    cost: Cost | null;
    evaluated_at: string;
  }[];
  observed_outcomes: {
    id: string;
    review_id: string;
    disposition: string;
    origin: string;
    reason: string;
    cost_basis: string;
    observed_end: string;
  }[];
  model: {
    attempts: number;
    actual_usd: string;
    pending_reserved_usd: string;
    p50_seconds: number | null;
    p95_seconds: number | null;
    basis: string;
  };
  bounds: string;
  billing: {
    totals: {
      currency: string;
      rows: number;
      billed: string | null;
      effective: string | null;
      negative_billed_rows: number;
    }[];
    groups: {
      provider: string;
      service: string;
      currency: string;
      rows: number;
      billed: string | null;
      effective: string | null;
    }[];
    note: string;
  };
}
