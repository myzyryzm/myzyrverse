import { useEffect, useRef, useState } from "react";
import type { Decision, Proposal, ResearchSource } from "../types";
import Rich from "./Rich";

export const DECISION_LABELS: Record<Decision, string> = {
  pending: "Not reviewed",
  accepted: "Accepted",
  modified: "Modify",
  rejected: "Rejected",
};

export const RESEARCHER_SHORT: Record<string, string> = {
  antiquarian: "Antiquarian",
  historian: "Historian",
  mythographer: "Mythographer",
  psychologist: "Psychologist",
};

const PART_LABELS: Record<string, string> = {
  characterization: "Characterization",
  plot: "Plot",
  world: "World",
  integration: "Integration with canon",
};

interface Props {
  proposals: Proposal[];
  start: number;
  sources: ResearchSource[];
  /** Decisions and notes can only change at the research gate; otherwise this is a read-only viewer. */
  editable: boolean;
  onChange: (next: Proposal[]) => void;
  onClose: () => void;
}

/** One card per proposal: cycle with the arrows, note each part, answer its questions, accept / modify / reject. */
export default function ProposalReview({ proposals, start, sources, editable, onChange, onClose }: Props) {
  const [idx, setIdx] = useState(Math.min(Math.max(start, 0), proposals.length - 1));
  const [needNote, setNeedNote] = useState(false);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const p = proposals[idx];
  const n = proposals.length;

  const go = (d: number) => { setNeedNote(false); setIdx((i) => (i + d + n) % n); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && e.target.closest("input, textarea, select");
      if (e.key === "Escape") { if (typing) (e.target as HTMLElement).blur(); else onClose(); return; }
      if (typing) return;
      if (e.key === "ArrowLeft") go(-1);
      if (e.key === "ArrowRight") go(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!p) return null;

  const patch = (change: Partial<Proposal>) => onChange(proposals.map((x, i) => (i === idx ? { ...x, ...change } : x)));
  const hasNotes = (x: Proposal) => !!x.note.trim() || x.parts.some((pt) => pt.note.trim());

  const decide = (decision: Decision) => {
    if (decision === "modified" && !hasNotes(p)) {
      setNeedNote(true);
      noteRef.current?.focus();
      return;
    }
    setNeedNote(false);
    const next = proposals.map((x, i) => (i === idx ? { ...x, decision } : x));
    onChange(next);
    if (decision === "pending") return;
    // Move on to the next card nobody has looked at yet, if there is one.
    for (let k = 1; k < n; k++) {
      const j = (idx + k) % n;
      if (next[j].decision === "pending") { setIdx(j); return; }
    }
  };

  const pending = proposals.filter((x) => x.decision === "pending").length;

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal review" role="dialog" aria-modal="true" aria-label="Review proposals">
        <div className="modal-head">
          <h2>Proposals</h2>
          <span className="hint">{editable ? `${pending} of ${n} not reviewed · ← → to move, Esc to close` : "read-only: decisions are made at the research gate"}</span>
          <button className="ghost" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="review-nav">
          <button className="ghost" onClick={() => go(-1)} aria-label="Previous proposal">←</button>
          <div className="review-dots">
            {proposals.map((x, i) => (
              <button key={x.id} className={`dot ${x.decision}${i === idx ? " current" : ""}`}
                      title={`${i + 1}. ${x.title} (${DECISION_LABELS[x.decision]})`} onClick={() => { setNeedNote(false); setIdx(i); }} />
            ))}
          </div>
          <span className="review-count">{idx + 1} / {n}</span>
          <button className="ghost" onClick={() => go(1)} aria-label="Next proposal">→</button>
        </div>

        <div className={`review-body${p.decision === "rejected" ? " rejected" : ""}`}>
          <div className="review-title">
            <span className="tag">{RESEARCHER_SHORT[p.researcher] ?? p.researcher}</span>
            <span className={`decision-chip ${p.decision}`}>{DECISION_LABELS[p.decision]}</span>
            <h3>{p.title}</h3>
          </div>
          {p.decision === "rejected" && (
            <div className="rejected-banner">
              Rejected. Later steps will not see this proposal.
              {editable && <button className="small" onClick={() => decide("pending")}>Undo</button>}
            </div>
          )}
          {p.pitch && <div className="pitch"><Rich text={p.pitch} sources={sources} /></div>}
          {p.affects.length > 0 && (
            <div className="chips"><span className="caption">affects</span>{p.affects.map((a) => <span key={a} className="tag">{a}</span>)}</div>
          )}

          {p.parts.map((pt, pi) => (
            <section key={pi} className={`part ${pt.label}`}>
              <h4>{PART_LABELS[pt.label] ?? pt.label}</h4>
              <Rich text={pt.text} sources={sources} />
              {(editable || pt.note) && (
                <textarea className="part-note" rows={2} readOnly={!editable} value={pt.note}
                          placeholder={`Your note on the ${(PART_LABELS[pt.label] ?? pt.label).toLowerCase()}…`}
                          onChange={(e) => patch({ parts: p.parts.map((x, j) => (j === pi ? { ...x, note: e.target.value } : x)) })} />
              )}
            </section>
          ))}

          {p.questions.length > 0 && (
            <section className="part questions">
              <h4>Questions this raises</h4>
              {p.questions.map((q, qi) => (
                <label key={qi} className="field">
                  <span className="q">{q.q}</span>
                  <input readOnly={!editable} value={q.answer} placeholder={editable ? "Your answer (leave blank to keep it open)" : "(unanswered)"}
                         onChange={(e) => patch({ questions: p.questions.map((x, j) => (j === qi ? { ...x, answer: e.target.value } : x)) })} />
                </label>
              ))}
            </section>
          )}
        </div>

        <div className="review-foot">
          <textarea ref={noteRef} className={needNote ? "need" : ""} rows={3} readOnly={!editable} value={p.note}
                    placeholder={editable ? "What you want done with this proposal: changes, conditions, what to keep or drop…" : "(no notes)"}
                    onChange={(e) => { patch({ note: e.target.value }); if (e.target.value.trim()) setNeedNote(false); }} />
          {needNote && <p className="hint warn-text">Modify needs a note saying what to change (here or on a part).</p>}
          {editable && (
            <div className="row decisions">
              <button className={`decide accepted${p.decision === "accepted" ? " on" : ""}`} onClick={() => decide("accepted")}>Accept</button>
              <button className={`decide modified${p.decision === "modified" ? " on" : ""}`} onClick={() => decide("modified")}>Modify</button>
              <button className={`decide rejected${p.decision === "rejected" ? " on" : ""}`} onClick={() => decide("rejected")}>Reject</button>
              {p.decision !== "pending" && <button className="ghost small" onClick={() => decide("pending")}>Clear decision</button>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
