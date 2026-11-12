import type {
  AppConfig, Hook, LedgerEntry, MetricsView, OpenQuestion, RunMeta, RunState, StoryEvent, TimelineItem, TimelinesView,
} from "./types";

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not json */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const enc = encodeURIComponent;

export const api = {
  config: () => req<AppConfig>("GET", "/config"),

  runs: () => req<RunMeta[]>("GET", "/runs"),
  createRun: (body: {
    id: string; type: string; title: string; brief: string; pov: string;
    researchers: string[]; target_event_id: string;
  }) => req<RunMeta>("POST", "/runs", body),
  deleteRun: (id: string) => req("DELETE", `/runs/${enc(id)}`),
  runState: (id: string) => req<RunState>("GET", `/runs/${enc(id)}/state`),
  start: (id: string) => req("POST", `/runs/${enc(id)}/start`),
  resume: (id: string, edits: Record<string, unknown>) => req("POST", `/runs/${enc(id)}/resume`, { edits }),
  retry: (id: string) => req("POST", `/runs/${enc(id)}/retry`),
  cancel: (id: string) => req("POST", `/runs/${enc(id)}/cancel`),
  regenerate: (id: string, notes: string) => req("POST", `/runs/${enc(id)}/regenerate`, { notes }),
  revert: (id: string) => req<{ warnings: string[] }>("POST", `/runs/${enc(id)}/revert`),
  restore: (id: string) => req("POST", `/runs/${enc(id)}/restore`),
  adoptLore: (id: string, file: string) => req<RunMeta>("POST", `/runs/${enc(id)}/adopt`, { file }),

  prehistory: () => req<Record<string, string>>("GET", "/lore/prehistory"),
  savePrehistory: (name: string, text: string) => req("PUT", `/lore/prehistory/${enc(name)}`, { text }),
  deletePrehistory: (name: string) => req("DELETE", `/lore/prehistory/${enc(name)}`),

  present: () => req<{ entries: LedgerEntry[]; markdown: string }>("GET", "/lore/present"),
  addPresent: (body: { run_id: string | null; entity: string; change: string; detail: string }) =>
    req("POST", "/lore/present/entries", body),

  questions: () => req<OpenQuestion[]>("GET", "/lore/open-questions"),
  addQuestion: (question: string, about: string) => req("POST", "/lore/open-questions", { question, about }),
  updateQuestion: (id: string, patch: Partial<OpenQuestion>) => req("PATCH", `/lore/open-questions/${enc(id)}`, patch),
  deleteQuestion: (id: string) => req("DELETE", `/lore/open-questions/${enc(id)}`),

  hooks: () => req<Hook[]>("GET", "/lore/hooks"),
  addHook: (text: string, about: string) => req<Hook>("POST", "/lore/hooks", { text, about }),
  deleteHook: (id: string) => req("DELETE", `/lore/hooks/${enc(id)}`),

  events: () => req<StoryEvent[]>("GET", "/lore/events"),
  addEvent: (body: Partial<StoryEvent>) => req<StoryEvent>("POST", "/lore/events", body),
  updateEvent: (id: string, patch: Partial<StoryEvent>) => req("PATCH", `/lore/events/${enc(id)}`, patch),
  deleteEvent: (id: string) => req("DELETE", `/lore/events/${enc(id)}`),

  timelines: () => req<TimelinesView>("GET", "/lore/timelines"),
  setLane: (lane: string, ids: string[]) => req<TimelinesView>("PUT", `/lore/timelines/${enc(lane)}`, { ids }),

  timeline: () => req<TimelineItem[]>("GET", "/timeline"),
  manuscript: () => req<{ text: string }>("GET", "/manuscript"),
  metrics: () => req<MetricsView>("GET", "/metrics"),
};
