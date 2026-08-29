// Talking to the twin.
//
// Two behaviours here are not incidental.
//
// A 409 is not an error. The twin returning "building the line state, 12 of the
// 20 cycles a baseline needs" is the twin working correctly on a cold start,
// and the interface renders that sentence rather than a failure. `ApiProblem`
// carries the sentence through so a view can show it as written.
//
// Nothing here retries silently. A view that quietly refetched until something
// appeared would be a view that showed a stale screen with no indication of it,
// and data age is the one thing this product never hides.

import type {
  Actions,
  BusinessCase,
  ConstraintMigration,
  CounterfactualResult,
  Evidence,
  Forecast,
  LineState,
  LineSummary,
  LossPareto,
  Notice,
  Realised,
  Recommendations,
  RetroTrace,
  SandboxOption,
  Scorecard,
  SensorRecommendations,
  Sites,
  StationDetail,
  TopologyDraft,
  UnitDetail,
  UnitsAtRisk,
} from '@/lib/types';

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

export class ApiProblem extends Error {
  readonly status: number;
  readonly title: string;
  readonly detail: string;

  constructor(status: number, title: string, detail: string) {
    super(detail || title);
    this.name = 'ApiProblem';
    this.status = status;
    this.title = title;
    this.detail = detail;
  }

  // A cold start and a station with too little history are both this. The
  // interface shows the detail sentence and keeps the rest of the screen.
  get isWaitingForHistory(): boolean {
    return this.status === 409;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
    cache: 'no-store',
  });
  if (!response.ok) {
    let title = 'The request could not be completed';
    let detail = `${response.status} from ${path}`;
    try {
      const body = await response.json();
      title = body.title ?? title;
      detail = body.detail ?? detail;
    } catch {
      // A response with no problem body still has a status worth reporting.
    }
    throw new ApiProblem(response.status, title, detail);
  }
  return (await response.json()) as T;
}

export const api = {
  lines: () => request<{ lines: LineSummary[] }>('/api/v1/lines'),
  state: (lineId: string) =>
    request<LineState>(`/api/v1/lines/${lineId}/state`),
  actions: (lineId: string) =>
    request<Actions>(`/api/v1/lines/${lineId}/actions`),
  unitsAtRisk: (lineId: string) =>
    request<UnitsAtRisk>(`/api/v1/lines/${lineId}/units-at-risk`),
  forecast: (lineId: string) =>
    request<Forecast>(`/api/v1/lines/${lineId}/forecast`),
  notices: (lineId: string) =>
    request<Notice[]>(`/api/v1/lines/${lineId}/notices`),
  evidence: (predictionId: string) =>
    request<Evidence>(`/api/v1/predictions/${predictionId}/evidence`),
  station: (lineId: string, stationId: string) =>
    request<StationDetail>(`/api/v1/lines/${lineId}/stations/${stationId}`),
  unit: (lineId: string, unitId: string) =>
    request<UnitDetail>(`/api/v1/lines/${lineId}/units/${unitId}`),
  scorecard: (lineId: string) =>
    request<Scorecard>(`/api/v1/lines/${lineId}/scorecard`),
  sensors: (lineId: string) =>
    request<SensorRecommendations>(
      `/api/v1/lines/${lineId}/sensor-recommendations`,
    ),
  retroTrace: (unitId: string) =>
    request<RetroTrace>(`/api/v1/units/${unitId}/retro-trace`),
  counterfactual: (
    lineId: string,
    options: SandboxOption[],
    replications?: number,
  ) =>
    request<CounterfactualResult>(`/api/v1/lines/${lineId}/counterfactual`, {
      method: 'POST',
      body: JSON.stringify({ options, replications, budget_ms: 5000 }),
    }),
  markExecuted: (runId: string, label: string, note: string) =>
    request<{ run_id: string }>(
      `/api/v1/counterfactual/${runId}/mark-executed`,
      { method: 'POST', body: JSON.stringify({ label, note }) },
    ),
  constraintMigration: (lineId: string) =>
    request<ConstraintMigration>(
      `/api/v1/lines/${lineId}/plan/constraint-migration`,
    ),
  lossPareto: (lineId: string, hours: number) =>
    request<LossPareto>(
      `/api/v1/lines/${lineId}/plan/loss-pareto?hours=${hours}`,
    ),
  recommendations: (lineId: string) =>
    request<Recommendations>(`/api/v1/lines/${lineId}/plan/recommendations`),
  sites: () => request<Sites>('/api/v1/program/sites'),
  businessCase: () => request<BusinessCase>('/api/v1/program/business-case'),
  recalculate: (values: Record<string, number>) =>
    request<BusinessCase>('/api/v1/program/business-case', {
      method: 'POST',
      body: JSON.stringify({ values }),
    }),
  realised: () => request<Realised>('/api/v1/program/realised'),
  topology: (lineId: string) =>
    request<TopologyDraft>(`/api/v1/lines/${lineId}/topology-draft`),
};

// The two exports that produce a file rather than a value. Both are plain links
// so that the browser handles the download and the interface does not have to
// hold a blob it cannot name.
export const exportUrls = {
  sensorQueue: (lineId: string) =>
    `${API_BASE}/api/v1/lines/${lineId}/sensor-recommendations/export`,
  containment: (unitId: string) =>
    `${API_BASE}/api/v1/units/${unitId}/retro-trace/export`,
  loss: (lineId: string, hours: number) =>
    `${API_BASE}/api/v1/lines/${lineId}/plan/loss-pareto/export?hours=${hours}`,
};

export function socketUrl(lineId: string): string {
  const base = API_BASE.replace(/^http/, 'ws');
  return `${base}/ws/lines/${lineId}`;
}
