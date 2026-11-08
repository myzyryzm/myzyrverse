/** Stable hue per character name so the same person has the same color everywhere. */
export function charHue(name: string): number {
  let h = 0;
  for (const c of name.toLowerCase()) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

export const GATE_LABELS: Record<string, string> = {
  human_gate_research: "Research review",
  human_gate_outline: "Outline review",
  human_gate_final: "Final prose review",
  human_gate_ledger: "Lore ledger review",
};

export const RUN_TYPE_LABELS: Record<string, string> = {
  chapter: "Chapter",
  research: "Research",
  plan_arc: "Arc plan",
  lore: "Lore",
};

export const RESEARCHER_LABELS: Record<string, string> = {
  antiquarian: "Antiquarian (Bronze Age grounding)",
  historian: "Historian (historical analogues)",
  mythographer: "Mythographer (fiction analogues)",
  psychologist: "Psychologist (character friction)",
};

export function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
}

export function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
