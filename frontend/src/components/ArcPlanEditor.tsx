import { useEffect, useState } from "react";
import type { ArcMilestone, ArcPlan } from "../types";

const EMPTY: ArcMilestone = { title: "", description: "", characters: [], follows_from: "" };

/** A plan from an older run may be plain text; show it as the overview. */
export function asPlan(raw: unknown): ArcPlan {
  if (typeof raw === "string") return { overview: raw, milestones: [], risks: [] };
  const p = (raw ?? {}) as Partial<ArcPlan>;
  return { overview: p.overview ?? "", milestones: p.milestones ?? [], risks: p.risks ?? [] };
}

interface Props {
  plan: ArcPlan;
  editable: boolean;
  onChange: (plan: ArcPlan) => void;
}

/** The arc plan at the outline gate: overview, milestones in story order, risks. */
export default function ArcPlanEditor({ plan, editable, onChange }: Props) {
  const ms = plan.milestones;
  const setMs = (next: ArcMilestone[]) => onChange({ ...plan, milestones: next });
  const patch = (i: number, p: Partial<ArcMilestone>) => setMs(ms.map((m, j) => (j === i ? { ...m, ...p } : m)));
  const move = (i: number, d: -1 | 1) => {
    const next = [...ms];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    setMs(next);
  };
  const ro = !editable;

  return (
    <div className="stack arc-plan">
      <label className="field">
        <span>Overview: the causal logic from the present to the target event</span>
        <textarea className={`editor notes${ro ? " readonly" : ""}`} readOnly={ro} value={plan.overview}
                  onChange={(e) => onChange({ ...plan, overview: e.target.value })} />
      </label>

      <div className="field"><span>Milestones, in story order. Each becomes a sub-event of the target event.</span></div>
      {ms.length === 0 && <p className="hint">No milestones{editable ? " yet. Add one below." : "."}</p>}
      {ms.map((m, i) => (
        <div key={i} className="card milestone">
          <div className="card-head">
            <span className="tag">{i + 1}</span>
            <input className="milestone-title" readOnly={ro} placeholder="Milestone title" value={m.title}
                   onChange={(e) => patch(i, { title: e.target.value })} />
            {editable && (
              <span className="row tight">
                <button className="small ghost" disabled={i === 0} title="Move up" onClick={() => move(i, -1)}>↑</button>
                <button className="small ghost" disabled={i === ms.length - 1} title="Move down" onClick={() => move(i, 1)}>↓</button>
                <button className="small ghost danger" title="Remove" onClick={() => setMs(ms.filter((_, j) => j !== i))}>✕</button>
              </span>
            )}
          </div>
          <label className="field">
            <span>What happens</span>
            <textarea readOnly={ro} value={m.description} onChange={(e) => patch(i, { description: e.target.value })} />
          </label>
          <label className="field">
            <span>Characters on whose timelines this lands (comma-separated; none = a world event)</span>
            <CharsInput value={m.characters} readOnly={ro} onChange={(characters) => patch(i, { characters })} />
          </label>
          <label className="field">
            <span>Follows from</span>
            <input readOnly={ro} value={m.follows_from} onChange={(e) => patch(i, { follows_from: e.target.value })} />
          </label>
        </div>
      ))}
      {editable && (
        <button className="small" onClick={() => setMs([...ms, { ...EMPTY }])}>+ Add milestone</button>
      )}

      <label className="field">
        <span>Risks: where the plan could feel contrived (one per line)</span>
        <RisksInput value={plan.risks} readOnly={ro} onChange={(risks) => onChange({ ...plan, risks })} />
      </label>
      {editable && (
        <p className="hint">
          After you press Resume, each milestone becomes a ticked sub-event row on the Ledger tab. Milestones without a
          title are dropped.
        </p>
      )}
    </div>
  );
}

const parseChars = (s: string) => s.split(",").map((c) => c.trim()).filter(Boolean);

/** Keeps the typed text (trailing commas and spaces) while reporting the parsed list. */
function CharsInput({ value, readOnly, onChange }: { value: string[]; readOnly: boolean; onChange: (v: string[]) => void }) {
  const [text, setText] = useState(value.join(", "));
  useEffect(() => {
    if (parseChars(text).join("|") !== value.join("|")) setText(value.join(", "));
  }, [value]);
  return <input readOnly={readOnly} value={text} placeholder="e.g. Tiye, Pentawere"
                onChange={(e) => { setText(e.target.value); onChange(parseChars(e.target.value)); }} />;
}

const parseLines = (s: string) => s.split("\n").map((l) => l.trim()).filter(Boolean);

function RisksInput({ value, readOnly, onChange }: { value: string[]; readOnly: boolean; onChange: (v: string[]) => void }) {
  const [text, setText] = useState(value.join("\n"));
  useEffect(() => {
    if (parseLines(text).join("\n") !== value.join("\n")) setText(value.join("\n"));
  }, [value]);
  return <textarea readOnly={readOnly} value={text}
                   onChange={(e) => { setText(e.target.value); onChange(parseLines(e.target.value)); }} />;
}
