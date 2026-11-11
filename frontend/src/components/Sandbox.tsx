import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { LedgerEntry, Proposal, RunState, RunType } from "../types";
import { GATE_LABELS, errMsg } from "../util";
import ProposalReview, { RESEARCHER_SHORT, normalizeDecision } from "./ProposalReview";
import ResearchReader from "./ResearchReader";

type TextField = "research_notes" | "chapter_outline" | "arc_plan" | "lore_doc" | "draft_prose" | "critique_notes" | "summary"
  | "author_research_notes";
type TabId = TextField | "ledger" | "sources" | `history-${number}`;

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
  sources: "Sources",
};

// What the outline gate edits, per run type.
const OUTLINE_FIELD: Partial<Record<RunType, TextField>> = { plan_arc: "arc_plan", lore: "lore_doc" };

const KINDS: LedgerEntry["kind"][] = ["lore", "answer", "new_question", "hook", "event_update", "sub_event"];

const KIND_GROUPS: Record<LedgerEntry["kind"], string> = {
  lore: "Lore",
  answer: "Answers to open questions",
  new_question: "New open questions",
  hook: "Hooks (ideas for later, not canon)",
  event_update: "Event progress",
  sub_event: "Milestones",
};

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
  const [proposals, setProposals] = useState<Proposal[] | null>(null);
  const [reviewAt, setReviewAt] = useState<number | null>(null);
  const [flashSrc, setFlashSrc] = useState<number | null>(null);

  // Drop local edits once the run moves on (they were sent with Resume, or discarded by Regenerate).
  useEffect(() => {
    if (runState?.running) {
      setDrafts({});
      setLedger(null);
      setChars(null);
      setProposals(null);
      setReviewAt(null);
    }
  }, [runState?.running]);

  useEffect(() => {
    if (editable) setTab(editable);
  }, [editable, gate]);

  const textValue = (f: TextField) => drafts[f] ?? (v[f] as string | undefined) ?? "";
  const ledgerValue = ledger ?? v.proposed_ledger ?? [];
  const charsValue = chars ?? (v.characters_present ?? []).join(", ");
  const proposalsValue = useMemo(() => (proposals ?? v.research_proposals ?? []).map(normalizeDecision), [proposals, v.research_proposals]);
  const undecided = proposalsValue.filter((p) => p.decision === "pending").length;
  const sources = v.research_sources ?? [];
  const structured = !!(v.research_background?.length || v.research_proposals?.length);
  const canDecide = gate === "human_gate_research";

  useEffect(() => {
    registerEdits(() => {
      const edits: Record<string, unknown> = {};
      for (const [k, val] of Object.entries(drafts)) {
        if (val !== undefined && val !== v[k]) edits[k] = val;
      }
      if (ledger) edits.proposed_ledger = ledger;
      if (proposals) edits.research_proposals = proposals;
      if (chars !== null) edits.characters_present = chars.split(",").map((s) => s.trim()).filter(Boolean);
      return edits;
    });
  }, [drafts, ledger, chars, proposals, v, registerEdits]);

  // A superscript was clicked: show the Sources tab and bring that source into view.
  useEffect(() => {
    if (flashSrc === null || tab !== "sources") return;
    document.getElementById(`src-${flashSrc}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    const t = setTimeout(() => setFlashSrc(null), 1600);
    return () => clearTimeout(t);
  }, [flashSrc, tab]);
  const showSource = (n: number) => { setTab("sources"); setFlashSrc(n); };

  const tabs = useMemo(() => {
    const t: TabId[] = [];
    const has = (f: string) => typeof v[f] === "string" && (v[f] as string).length > 0;
    // Always present at a gate: your notes on the research live on this tab and stay editable at every gate.
    if (has("research_notes") || editable === "research_notes" || gate) t.push("research_notes");
    if (v.research_sources?.length) t.push("sources");
    if (has("arc_plan") || editable === "arc_plan") t.push("arc_plan");
    if (has("lore_doc") || editable === "lore_doc") t.push("lore_doc");
    if (has("chapter_outline") || editable === "chapter_outline") t.push("chapter_outline");
    if (has("draft_prose") || editable === "draft_prose") t.push("draft_prose");
    if (has("critique_notes")) t.push("critique_notes");
    if (v.proposed_ledger?.length || editable === "ledger") t.push("ledger");
    (v.draft_history ?? []).forEach((_, i) => t.push(`history-${i}`));
    return t;
  }, [v, editable, gate]);

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


        {active === "sources" && (
          <ol className="sources">
            {sources.map((s) => (
              <li key={s.n} id={`src-${s.n}`} value={s.n} className={flashSrc === s.n ? "flash" : ""}>
                {s.url && /^https?:/.test(s.url)
                  ? <a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a>
                  : <span>{s.title}{s.url && s.url !== s.title ? ` (${s.url})` : ""}</span>}
                {" "}{s.researchers.map((r) => <span key={r} className="tag">{RESEARCHER_SHORT[r] ?? r}</span>)}
              </li>
            ))}
          </ol>
        )}

        {active && active !== "ledger" && active !== "sources" && !active.startsWith("history-") && (
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
            {active === "research_notes" && structured ? (
              <ResearchReader background={v.research_background ?? []} proposals={proposalsValue} sources={sources}
                              cut={v.research_proposals_cut ?? []} editable={canDecide} onOpen={setReviewAt} onRef={showSource}
                              onChange={setProposals} />
            ) : (
              <textarea
                className={`editor prose${active === editable ? "" : " readonly"}${active === "research_notes" ? " research" : ""}`}
                readOnly={active !== editable}
                value={textValue(active as TextField)}
                placeholder={active === "research_notes" && !textValue("research_notes") ? "(no research for this run)" : undefined}
                onChange={(e) => setDrafts({ ...drafts, [active]: e.target.value })}
              />
            )}
            {active === editable && drafts[active as TextField] !== undefined && drafts[active as TextField] !== v[active] && (
              <div className="hint">Edited. Your version is sent when you press Resume.</div>
            )}
            {active === "research_notes" && canDecide && undecided > 0 && (
              <div className="hint warn-text">
                {undecided} proposal{undecided > 1 ? "s" : ""} still need{undecided > 1 ? "" : "s"} a decision before you can resume.
              </div>
            )}
            {active === "research_notes" && proposals && canDecide && !undecided && (
              <div className="hint">Proposal decisions edited. They are sent when you press Resume.</div>
            )}
            {active === "research_notes" && (
              <>
                <label className="field author-notes">
                  <span>Your notes on the research: answers, decisions, corrections. They steer every later step.</span>
                  <textarea
                    className={`editor notes${gate ? "" : " readonly"}`}
                    readOnly={!gate}
                    placeholder={gate ? "e.g. Tiye's lover is the Sherden captain, not the noble. Drop the Knossos idea: Jon trains at Tyre."
                      : "Editable while the run is paused at a gate."}
                    value={textValue("author_research_notes")}
                    onChange={(e) => setDrafts({ ...drafts, author_research_notes: e.target.value })}
                  />
                </label>
                <div className="hint">
                  {drafts.author_research_notes !== undefined && drafts.author_research_notes !== (v.author_research_notes ?? "")
                    ? "Edited. Sent when you press Resume, then placed above every later agent's task."
                    : "Editable at any gate. Sent on Resume and placed above every later agent's task."}
                </div>
              </>
            )}
          </>
        )}

        {reviewAt !== null && proposalsValue.length > 0 && (
          <ProposalReview proposals={proposalsValue} start={reviewAt} sources={sources} editable={canDecide}
                          onChange={setProposals} onClose={() => setReviewAt(null)} />
        )}

        {active?.startsWith("history-") && (
          <textarea className="editor prose readonly" readOnly value={(v.draft_history ?? [])[Number(active.split("-")[1])] ?? ""} />
        )}

        {active === "ledger" && (
          <div className="stack">
            <p className="hint">
              Proposed changes to the present lore, open questions, hooks and events. Everything is ticked; untick what you don't want added,
              edit anything, add your own rows.
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
              <div key={i} className="stack tight">
              {(i === 0 || ledgerValue[i - 1].kind !== e.kind) && <h4 className="ledger-group">{KIND_GROUPS[e.kind] ?? e.kind}</h4>}
              <div className={`ledger-row${e.accepted === false ? " rejected" : ""}`}>
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
                {e.kind === "sub_event" && (
                  <CharactersInput value={e.characters ?? []} readOnly={editable !== "ledger"}
                                   onChange={(characters) => setLedgerRow(i, { characters })} />
                )}
              </div>
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

/** Comma-separated names; keeps the raw text while typing so commas and spaces are not swallowed. */
function CharactersInput({ value, readOnly, onChange }: {
  value: string[]; readOnly: boolean; onChange: (v: string[]) => void;
}) {
  const [text, setText] = useState(value.join(", "));
  return (
    <input placeholder="characters on whose timelines this lands, comma separated" value={text} readOnly={readOnly}
           onChange={(e) => {
             setText(e.target.value);
             onChange(e.target.value.split(",").map((x) => x.trim()).filter(Boolean));
           }} />
  );
}
