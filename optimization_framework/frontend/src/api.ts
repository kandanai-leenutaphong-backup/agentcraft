import { z } from 'zod';

const measurement = z.number().finite().nullable();
const candidateSchema = z.object({
  id: z.string(), parent_id: z.string().nullable(), name: z.string(), digest: z.string(),
  status: z.enum(['passed', 'failed']), hypothesis: z.string(), diff: z.string(),
  checks: z.array(z.object({ name: z.string(), status: z.enum(['passed', 'failed', 'blocked']), detail: z.string() })),
});
export const runSchema = z.object({
  id: z.string(), task_id: z.string(), task_name: z.string(), domain: z.string(),
  status: z.enum(['running', 'completed', 'failed', 'cancelled', 'blocked', 'timed_out']),
  acceptance: z.enum(['passed', 'failed', 'not_verified']),
  decision: z.enum(['improved', 'no_improvement', 'regressed', 'inconclusive']),
  evidence_class: z.enum(['synthetic-integration', 'local-live', 'deployed-live']),
  executor: z.enum(['deterministic', 'copilot']), created_at: z.string(), updated_at: z.string(),
  metrics: z.object({
    elapsed_seconds: measurement, repair_cycles: measurement, actions: measurement, calls: measurement,
    files_changed: measurement, lines_added: measurement, lines_deleted: measurement,
    first_pass_success: z.boolean().nullable(), model_requests: measurement, telemetry_coverage: z.string(),
  }),
  candidates: z.array(candidateSchema),
  events: z.array(z.object({ id: z.string(), at: z.string(), kind: z.string(), detail: z.string(), candidate_id: z.string().nullable() })),
  feedback: z.array(z.object({
    id: z.string(), at: z.string(), author: z.string(), text: z.string(), candidate_id: z.string().nullable(),
    disposition: z.string().nullable(), reason: z.string().nullable(),
  })),
  selected_candidate_id: z.string().nullable(), limitations: z.array(z.string()),
  restorations: z.array(z.object({ at: z.string(), candidate_id: z.string(), verified: z.boolean() })),
});
const tasksSchema = z.object({ tasks: z.array(z.object({ id: z.string(), name: z.string(), description: z.string(), domain: z.string() })) });
const runsSchema = z.object({ runs: z.array(runSchema) });
export type Run = z.infer<typeof runSchema>;
export type Candidate = z.infer<typeof candidateSchema>;
export type Task = z.infer<typeof tasksSchema>['tasks'][number];
export type Disposition = 'apply' | 'clarify' | 'defer' | 'decline';

export class ApiError extends Error {
  constructor(message: string, public readonly status: number | null) { super(message); }
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', ...init });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError('Connection unavailable. Request outcome may be unknown; retry uses the same request key.', null);
  }
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(`HTTP ${response.status}: ${text.slice(0, 1200) || response.statusText}`, response.status);
  }
  try { return await response.json(); }
  catch { throw new ApiError('Invalid JSON response from API.', response.status); }
}

function parse<Schema extends z.ZodType>(schema: Schema, value: unknown): z.infer<Schema> {
  const result = schema.safeParse(value);
  if (!result.success) {
    throw new ApiError(`API contract mismatch: ${result.error.issues.map(issue => `${issue.path.join('.')}: ${issue.message}`).join('; ')}`, null);
  }
  return result.data;
}

async function post(path: string, body: object): Promise<Run> {
  return parse(runSchema, await request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }));
}

const runPath = (id: string) => `/api/runs/${encodeURIComponent(id)}`;
export const api = {
  tasks: async (signal?: AbortSignal) => parse(tasksSchema, await request('/api/tasks', { signal })).tasks,
  runs: async (signal?: AbortSignal) => parse(runsSchema, await request('/api/runs', { signal })).runs,
  run: async (id: string, signal?: AbortSignal) => parse(runSchema, await request(runPath(id), { signal })),
  start: (task_id: string, idempotency_key: string) => post('/api/runs', { task_id, executor: 'deterministic', idempotency_key }),
  cancel: (id: string) => post(`${runPath(id)}/cancel`, {}),
  restore: (id: string, candidate_id: string, idempotency_key: string) => post(`${runPath(id)}/restore`, { candidate_id, idempotency_key }),
  feedback: (id: string, text: string, candidate_id: string | null, idempotency_key: string) => post(`${runPath(id)}/feedback`, { text, candidate_id, idempotency_key }),
  respond: (id: string, feedbackId: string, disposition: Disposition, reason: string, candidate_id: string | null, idempotency_key: string) => post(`${runPath(id)}/feedback/${encodeURIComponent(feedbackId)}/respond`, { disposition, reason, candidate_id, idempotency_key }),
  reportUrl: (id: string, format: 'json' | 'csv' | 'html') => `${runPath(id)}/report?format=${format}`,
};