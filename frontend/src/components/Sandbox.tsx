import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { LedgerEntry, RunState, RunType } from "../types";
import { GATE_LABELS, errMsg } from "../util";

type TextField = "research_notes" | "chapter_outline" | "arc_plan" | "lore_doc" | "draft_prose" | "critique_notes" | "summary";
type TabId = TextField | "ledger" | `history-${number}`;

const GATE_FIELD: Record<string, TextField | "ledger"> = {
  human_gate_research: "research_notes",
  human_gate_final: "draft_prose",
  human_gate_ledger: "ledger",
};

const TAB_LABELS: Record<string, string> = {
  research_notes: "Research",
  chapter_outline: "Outline",
  arc_plan: "Arc plan",
  lore_doc: "Lore doc",
  draft_prose: "Prose",
  critique_notes: "Critique",
  summary: "Summary",
  ledger: "Ledger",
};

// What the outline gate edits, per run type.
const OUTLINE_FIELD: Partial<Record<RunType, TextField>> = { plan_arc: "arc_plan", lore: "lore_doc" };

const KINDS: LedgerEntry["kind"][] = ["lore", "answer", "new_question", "event_update", "sub_event"];

interface Props {
  runState: RunState | null;
  registerEdits: (fn: () => Record<string, unknown>) => void;
  act: (fn: () => Promise<unknown>, after?: (r: unknown) => void) => Promise<void>;
}

export default function Sandbox({ runState, registerEdits, act }: Props) {
  const v = runState?.values ?? {};
  const gate = runState && !runState.running ? runState.next[0] : undefined;
  const runType = runState?.meta.type;
  const editable: TextField | "ledger" | undefined = gate
    ? gate === "human_gate_outline" ? (runType && OUTLINE_FIELD[runType]) ?? "chapter_outline" : GATE_FIELD[gate]
    : undefined;
  const canAdopt = runType === "lore" && (gate === "human_gate_ledger" || runState?.meta.status === "committed");

  const [drafts, setDrafts] = useState<Partial<Record<TextField, string>>>({});
  const [ledger, setLedger] = useState<LedgerEntry[] | null>(null);
  const [chars, setChars] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId | null>(null);

  // Drop local edits once the run moves on (they were sent with Resume, or discarded by Regenerate).
  useEffect(() => {
    if (runState?.running) {
      setDrafts({});
      setLedger(null);
      setChars(null);
    }
  }, [runState?.running]);

  useEffect(() => {
    if (editable) setTab(editable);
  }, [editable, gate]);

  const textValue = (f: TextField) => drafts[f] ?? (v[f] as string | undefined) ?? "";
  const ledgerValue = ledger ?? v.proposed_ledger ?? [];
  const charsValue = chars ?? (v.characters_present ?? []).join(", ");

  useEffect(() => {
    registerEdits(() => {
      const edits: Record<string, unknown> = {};
      for (const [k, val] of Object.entries(drafts)) {
        if (val !== undefined && val !== v[k]) edits[k] = val;
      }
      if (ledger) edits.proposed_ledger = ledger;
      if (chars !== null) edits.characters_present = chars.split(",").map((s) => s.trim()).filter(Boolean);
      return edits;
    });
  }, [drafts, ledger, chars, v, registerEdits]);

  const tabs = useMemo(() => {
    const t: TabId[] = [];
    const has = (f: string) => typeof v[f] === "string" && (v[f] as string).length > 0;
    if (has("research_notes") || editable === "research_notes") t.push("research_notes");
    if (has("arc_plan") || editable === "arc_plan") t.push("arc_plan");
    if (has("lore_doc") || editable === "lore_doc") t.push("lore_doc");
    if (has("chapter_outline") || editable === "chapter_outline") t.push("chapter_outline");
    if (has("draft_prose") || editable === "draft_prose") t.push("draft_prose");
    if (has("critique_notes")) t.push("critique_notes");
    if (v.proposed_ledger?.length || editable === "ledger") t.push("ledger");
    (v.draft_history ?? []).forEach((_, i) => t.push(`history-${i}`));
    return t;
  }, [v, editable]);

  const active: TabId | undefined = tab && tabs.includes(tab) ? tab : tabs[tabs.length - 1];

  if (!runState) {
    return (
      <>
        <div className="col-title">The Sandbox</div>
        <div className="col-body empty-state">
          <p>Select or create a run in the control deck.</p>
          <p className="muted">When a run pauses at a gate, its output appears here for you to edit before resuming.</p>
        </div>
      </>
    );
  }

  const setLedgerRow = (i: number, patch: Partial<LedgerEntry>) =>
    setLedger(ledgerValue.map((e, j) => (j === i ? { ...e, ...patch } : e)));

  return (
    <>
      <div className="col-title">
        The Sandbox
        {gate && <span className="badge gate">{GATE_LABELS[gate]} · editable</span>}
        {runState.running && <span className="badge running">working…</span>}
      </div>
      <nav className="tabs">
        {tabs.map((t) => (
          <button key={t} className={`${active === t ? "active" : ""}${t === editable ? " editable" : ""}`} onClick={() => setTab(t)}>
            {t.startsWith("history-") ? `Draft ${Number(t.split("-")[1]) + 1}` : TAB_LABELS[t]}
            {t === editable ? " ✎" : ""}
          </button>
        ))}
      </nav>
      <div className="col-body">
        {!active && (
          <div className="empty-state">
            {runState.started ? <p className="muted">Waiting for the first output…</p>
              : <p>Not started. Press <b>Start</b> in the control deck.</p>}
          </div>
        )}


        {active && active !== "ledger" && !active.startsWith("history-") && (
          <>
            {active === "lore_doc" && canAdopt && (
              <AdoptLore runId={runState.meta.id} adoptedTo={runState.meta.adopted_to ?? null} act={act} />
            )}
            {active === "draft_prose" && v.critique_notes && (
              <details className="critique-peek" open={v.critique_verdict === "FAILED"}>
                <summary>Critic: {v.critique_verdict || "n/a"} after {(v.revision_count ?? 0) + 1} draft(s)</summary>
                <pre>{v.critique_notes}</pre>
              </details>
            )}
            <textarea
              className={`editor prose${active === editable ? "" : " readonly"}`}
              readOnly={active !== editable}
              value={textValue(active as TextField)}
              onChange={(e) => setDrafts({ ...drafts, [active]: e.target.value })}
            />
            {active === editable && drafts[active as TextField] !== undefined && drafts[active as TextField] !== v[active] && (
              <div className="hint">Edited. Your version is sent when you press Resume.</div>
            )}
          </>
        )}

        {active?.startsWith("history-") && (
          <textarea className="editor prose readonly" readOnly value={(v.draft_history ?? [])[Number(active.split("-")[1])] ?? ""} />
        )}

        {active === "ledger" && (
          <div className="stack">
            <p className="hint">
              Proposed changes to the present lore, open questions and events. Untick what you reject, edit anything, add your own rows.
              Commit writes the ticked rows, linked to this run.
            </p>
            <label className="field">
              <span>Summary (feeds later chapters)</span>
              <textarea readOnly={editable !== "ledger"} value={drafts.summary ?? v.summary ?? ""}
                        onChange={(e) => setDrafts({ ...drafts, summary: e.target.value })} />
            </label>
            <label className="field">
              <span>Characters present (timeline)</span>
              <input readOnly={editable !== "ledger"} value={charsValue} onChange={(e) => setChars(e.target.value)} />
            </label>
            {ledgerValue.map((e, i) => (
              <div key={i} className={`ledger-row${e.accepted === false ? " rejected" : ""}`}>
                <div className="row">
                  <input type="checkbox" checked={e.accepted !== false} disabled={editable !== "ledger"}
                         onChange={(ev) => setLedgerRow(i, { accepted: ev.target.checked })} />
                  <select value={e.kind} disabled={editable !== "ledger"}
                          onChange={(ev) => setLedgerRow(i, { kind: ev.target.value as LedgerEntry["kind"] })}>
                    {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                  </select>
                  <input className="grow" placeholder="entity" value={e.entity} readOnly={editable !== "ledger"}
                         onChange={(ev) => setLedgerRow(i, { entity: ev.target.value })} />
                  <input placeholder="change" value={e.change} readOnly={editable !== "ledger"}
                         onChange={(ev) => setLedgerRow(i, { change: ev.target.value })} />
                  {(e.kind === "answer" || e.kind === "event_update") && (
                    <input placeholder="ref id" value={e.ref_id} readOnly={editable !== "ledger"}
                           onChange={(ev) => setLedgerRow(i, { ref_id: ev.target.value })} />
                  )}
                  <span className={`tag ${e.source ?? "ai"}`}>{e.source ?? "ai"}{e.confidence ? ` · ${e.confidence}` : ""}</span>
                  {editable === "ledger" && (
                    <button className="ghost small danger" onClick={() => setLedger(ledgerValue.filter((_, j) => j !== i))}>×</button>
                  )}
                </div>
                <textarea value={e.detail} readOnly={editable !== "ledger"}
                          onChange={(ev) => setLedgerRow(i, { detail: ev.target.value })} />
              </div>
            ))}
            {editable === "ledger" && (
              <button onClick={() => setLedger([...ledgerValue, {
                kind: "lore", entity: "", change: "", detail: "", ref_id: "", source: "user", accepted: true,
              }])}>+ Add row</button>
            )}
          </div>
        )}
      </div>
    </>
  );
}

const NEW_FILE = "__new__";

/** Append the approved lore document to a prehistory file. The AI never does this on its own. */
function AdoptLore({ runId, adoptedTo, act }: { runId: string; adoptedTo: string | null; act: Props["act"] }) {
  const [files, setFiles] = useState<string[]>([]);
  const [choice, setChoice] = useState("");
  const [newName, setNewName] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.prehistory().then((f) => {
      const names = Object.keys(f);
      setFiles(names);
      setChoice((c) => c || adoptedTo || names[0] || NEW_FILE);
    }).catch((e) => setErr(errMsg(e)));
  }, [adoptedTo]);

  const target = choice === NEW_FILE ? newName.trim() : choice;
  const adopt = () => act(() => api.adoptLore(runId, target), () => setNewName(""));

  return (
    <div className="stack">
      <div className="row">
        <span className="hint">Adopt into prehistory:</span>
        <select value={choice} onChange={(e) => setChoice(e.target.value)}>
          {files.map((f) => <option key={f} value={f}>{f}.md</option>)}
          <option value={NEW_FILE}>new file…</option>
        </select>
        {choice === NEW_FILE && <input placeholder="file name" value={newName} onChange={(e) => setNewName(e.target.value)} />}
        <button className="primary" disabled={!target} onClick={adopt}>{adoptedTo ? "Adopt again" : "Adopt"}</button>
        {adoptedTo && <span className="badge">adopted to {adoptedTo}.md</span>}
      </div>
      <p className="hint">Appends the approved document (with your outline-gate edits) to the end of the file. Edit it there afterwards.</p>
      {err && <p className="hint">{err}</p>}
    </div>
  );
}
