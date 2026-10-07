// Adapted from the original ProofOps research template; see docs/data_sources.md.
// Only the dedicated local reporting API is an authorized target for this runner.
import http from 'k6/http';
import { check } from 'k6';
import execution from 'k6/execution';
import { Counter, Rate, Trend } from 'k6/metrics';

const baseUrl = (__ENV.TARGET_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
if ((__ENV.PROOFOPS_MODE || 'local') !== 'local' || __ENV.PROOFOPS_PUBLIC_DEMO === 'true') {
  throw new Error('Workload tests are disabled in hosted/public-demo mode.');
}
if (!/^http:\/\/((127\.0\.0\.1|localhost):(8080|18080)|workload:8080)$/.test(baseUrl)) {
  throw new Error('This workload is restricted to the dedicated local target.');
}
const runId = __ENV.RUN_ID || 'baseline-smoke-01';
if (!/^[a-zA-Z0-9._-]+$/.test(runId)) throw new Error('RUN_ID must be a simple file-safe label');
if (!['smoke', 'full'].includes(__ENV.PROFILE || 'smoke')) throw new Error('PROFILE must be smoke or full');
const smoke = (__ENV.PROFILE || 'smoke') === 'smoke';
const started = new Counter('reports_started');
const completed = new Counter('reports_completed');
const correct = new Counter('successful_reports');
const failures = new Counter('reports_http_failures');
const successRate = new Rate('report_success');
const wrong = new Counter('wrong_successful_results');
const classes = {};
for (const name of ['small', 'medium', 'large']) {
  classes[name] = {
    latency: new Trend(`report_latency_${name}`, true),
    completed: new Counter(`reports_completed_${name}`),
    correct: new Counter(`reports_correct_${name}`),
  };
}
http.setResponseCallback(http.expectedStatuses(200));

export const options = {
  scenarios: smoke ? {
    smoke: { executor: 'shared-iterations', vus: 1, iterations: 20, maxDuration: '2m' },
  } : {
    workday_and_peak: {
      executor: 'ramping-arrival-rate', startRate: 5, timeUnit: '1s',
      preAllocatedVUs: 30, maxVUs: 200,
      stages: [
        { duration: '2m', target: 20 }, { duration: '3m', target: 50 },
        { duration: '2m', target: 100 }, { duration: '1m', target: 20 },
      ],
      gracefulStop: '30s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<250'], http_req_failed: ['rate<0.01'],
    report_latency_small: ['p(95)<250'], report_latency_medium: ['p(95)<250'],
    report_latency_large: ['p(95)<250'], report_success: ['rate>=0.99'],
    wrong_successful_results: ['count==0'],
    successful_reports: [smoke ? 'count==20' : 'count>=10000'],
    ...(smoke ? {} : { dropped_iterations: ['count==0'] }),
  },
  summaryTrendStats: ['min', 'med', 'avg', 'max', 'p(90)', 'p(95)', 'p(99)'],
  tags: { run_id: runId, profile: smoke ? 'smoke' : 'workday-and-peak-v1' },
};

export function buildRequest(index) {
  const slot = index % 20;
  const count = slot < 16 ? 50 : slot < 19 ? 300 : 1500;
  const items = [];
  let expectedTotal = 0;
  for (let i = 0; i < count; i += 1) {
    const cents = ((i * 37 + (index % 100)) % 20000) - 1000;
    expectedTotal += cents;
    items.push({ item_id: `item-${i}`, amount_cents: cents });
  }
  return {
    body: { request_id: `${runId}-${index}`, currency: 'USD', items },
    expectedTotal, count,
    requestClass: slot < 16 ? 'small' : slot < 19 ? 'medium' : 'large',
  };
}

export default function () {
  const request = buildRequest(execution.scenario.iterationInTest);
  const headers = { 'Content-Type': 'application/json' };
  if (__ENV.TEST_API_TOKEN) headers.Authorization = `Bearer ${__ENV.TEST_API_TOKEN}`;
  started.add(1);
  const response = http.post(`${baseUrl}/v1/reports/summary`, JSON.stringify(request.body), {
    headers, timeout: '10s', tags: { name: 'report_summary', request_class: request.requestClass },
  });
  let body;
  try { body = response.json(); } catch (_) { body = null; }
  const valid = response.status === 200 && body !== null &&
    body.request_id === request.body.request_id && body.currency === 'USD' &&
    body.item_count === request.count && body.total_cents === request.expectedTotal;
  check(response, { 'report result is correct and complete': () => valid });
  completed.add(1);
  correct.add(valid ? 1 : 0);
  failures.add(response.status !== 200 ? 1 : 0);
  successRate.add(valid);
  wrong.add(response.status === 200 && !valid ? 1 : 0);
  classes[request.requestClass].latency.add(response.timings.duration);
  classes[request.requestClass].completed.add(1);
  classes[request.requestClass].correct.add(valid ? 1 : 0);
}

export function handleSummary(data) {
  const failed = [];
  for (const [name, metric] of Object.entries(data.metrics)) {
    for (const [rule, outcome] of Object.entries(metric.thresholds || {})) {
      if (!outcome.ok) failed.push(`${name}: ${rule}`);
    }
  }
  return {
    [`${runId}.k6-summary.json`]: JSON.stringify({
      run_id: runId, profile: smoke ? 'smoke' : 'workday-and-peak-v1', target: baseUrl,
      thresholds_failed: failed,
      scope: 'Local observation. Smoke establishes connectivity/correctness only; no AWS bound or billed saving is measured.',
      k6: data,
    }, null, 2),
    stdout: `${runId}: ${failed.length ? 'thresholds failed: ' + failed.join('; ') : 'configured thresholds met'}\n`,
  };
}
