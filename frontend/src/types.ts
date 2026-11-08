export type RunType = "chapter" | "research" | "plan_arc" | "lore";
export type RunStatus = "draft" | "committed" | "reverted";

export interface RunMeta {
  id: string;
  type: RunType;
  title: string;
  pov: string;
  researchers: string[];
  target_event_id: string;
  characters_present: string[];
  order: number | null;
  status: RunStatus;
  created_at: string;
  committed_at: string | null;
  adopted_to?: string | null;
  adopted_at?: string | null;
  running?: boolean;
}

export interface LedgerEntry {
  id?: string;
  kind: "lore" | "answer" | "new_question" | "event_update" | "sub_event";
  entity: string;
  change: string;
  detail: string;
  ref_id: string;
  characters?: string[];
  confidence?: "low" | "medium" | "high";
  source?: "ai" | "user";
  accepted?: boolean;
  run_id?: string | null;
  run_title?: string;
}

export interface UsageRecord {
  node: string;
  model: string;
  cost_usd: number | null;
  duration_ms: number | null;
  num_turns: number | null;
}

export interface RunValues {
  run_type?: RunType;
  review_status?: string;
  research_notes?: string;
  chapter_outline?: string;
  arc_plan?: string;
  lore_doc?: string;
  draft_prose?: string;
  draft_history?: string[];
  critique_notes?: string;
  critique_verdict?: string;
  revision_count?: number;
  proposed_ledger?: LedgerEntry[];
  summary?: string;
  characters_present?: string[];
  author_research_notes?: string;
  [key: string]: unknown;
}

export interface LogLine {
  t: number;
  kind: string;
  msg: string;
}

export interface RunState {
  meta: RunMeta;
  started: boolean;
  values: RunValues;
  next: string[];
  running: boolean;
  error: string | null;
  log: LogLine[];
  usage: UsageRecord[];
  cost_usd: number;
}

export interface OpenQuestion {
  id: string;
  question: string;
  about: string;
  status: "open" | "answered";
  answer: string;
  answered_by_run: string | null;
  created_by: "user" | "ai";
  source_run: string | null;
}

export type EventCategory = "world" | "personal";

export interface StoryEvent {
  id: string;
  title: string;
  description: string;
  scope: "arc" | "chapter";
  category: EventCategory;
  parent_id: string | null;
  characters: string[];
  target_run: string;
  order: number;
  status: "planned" | "in_progress" | "resolved";
  created_by: "user" | "ai";
  source_run: string | null;
  progress?: { run_id: string; detail: string }[];
}

export interface TimelineItem {
  run_id: string;
  order: number;
  title: string;
  pov: string;
  characters_present: string[];
  status: RunStatus;
}

export interface AppConfig {
  fake_llm: boolean;
  researchers: string[];
  models: Record<string, string>;
  max_revisions: number;
}

export interface NewRunPrefill {
  type: RunType;
  target_event_id?: string;
  title?: string;
  brief?: string;
}

export interface StoryOrder {
  levels: string[][];
  cycle: string[] | null;
}

export interface TimelinesView {
  characters: string[];
  /** The order the author placed events in, per lane. Only these create story order. */
  lanes: Record<string, string[]>;
  /** Events that belong on the lane (the character takes part, or a world event) but are not placed yet. */
  unplaced: Record<string, string[]>;
  story_order: StoryOrder;
}
