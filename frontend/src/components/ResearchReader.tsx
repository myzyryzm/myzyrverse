import { useState } from "react";
import type { BackgroundSection, Proposal, ResearchSource } from "../types";
import { RESEARCHER_SHORT, decisionLabel } from "./ProposalReview";
import Rich from "./Rich";

interface Props {
  background: BackgroundSection[];
  proposals: Proposal[];
  sources: ResearchSource[];
  /** Proposals the research editor left out. */
  cut: Proposal[];
  editable: boolean;
  onOpen: (index: number) => void;
  onRef: (n: number) => void;
  onChange: (next: Proposal[]) => void;
}

/** The research split into background (context) and proposals (the story ideas you decide on). */
export default function ResearchReader({ background, proposals, sources, cut, editable, onOpen, onRef, onChange }: Props) {
  const [view, setView] = useState<"background" | "proposals">(proposals.length ? "proposals" : "background");
  const pending = proposals.filter((p) => p.decision === "pending").length;
  const researchers = [...new Set(background.map((b) => b.researcher))];
  const firstPending = Math.max(0, proposals.findIndex((p) => p.decision === "pending"));
  const shown = new Set(proposals.map((p) => p.id));
  const leftOut = cut.filter((p) => !shown.has(p.id));

  return (
    <div className="reader">
      <div className="reader-bar">
        <div className="seg">
          <button className={view === "background" ? "on" : ""} onClick={() => setView("background")}>
            Background <span className="count">{background.length}</span>
          </button>
          <button className={view === "proposals" ? "on" : ""} onClick={() => setView("proposals")}>
            Proposals <span className="count">{proposals.length}</span>
          </button>
        </div>
        {proposals.length > 0 && (
          <button className={editable && pending ? "primary" : ""} onClick={() => onOpen(firstPending)}>
            {editable ? (pending ? `Review proposals (${pending} not reviewed)` : "Review proposals") : "View proposals"}
          </button>
        )}
      </div>

      {view === "background" && (
        <>
          {researchers.length > 1 && (
            <div className="chips jump">
              <span className="caption">jump to</span>
              {researchers.map((r) => (
                <button key={r} className="small ghost" onClick={() => document.getElementById(`bg-${r}`)?.scrollIntoView({ behavior: "smooth" })}>
                  {RESEARCHER_SHORT[r] ?? r}
                </button>
              ))}
            </div>
          )}
          <p className="hint">Context only. Nothing here is decided; story ideas are under Proposals.</p>
          {researchers.map((r) => (
            <section key={r} id={`bg-${r}`} className="bg-group">
              <h3>{RESEARCHER_SHORT[r] ?? r}</h3>
              {background.filter((b) => b.researcher === r).map((b, i) => (
                <details key={i} className="bg-section" open>
                  <summary>{b.heading || "Notes"}</summary>
                  <Rich text={b.body} sources={sources} onRef={onRef} />
                </details>
              ))}
            </section>
          ))}
          {!background.length && <p className="muted">No background in this research.</p>}
        </>
      )}

      {view === "proposals" && (
        <div className="proposal-list">
          {proposals.map((p, i) => (
            <button key={p.id} className={`proposal-card ${p.decision}`} onClick={() => onOpen(i)}>
              <div className="card-head">
                <span className="tag">{RESEARCHER_SHORT[p.researcher] ?? p.researcher}</span>
                <strong className="grow">{p.title}</strong>
                <span className={`decision-chip ${p.decision}`}>{decisionLabel(p)}</span>
              </div>
              {p.pitch && <Rich text={p.pitch} sources={sources} />}
              <div className="chips">
                {p.parts.map((pt, j) => <span key={j} className={`part-tag ${pt.label}`}>{pt.label}</span>)}
                {(p.also_from ?? []).map((r) => <span key={r} className="part-tag">also {RESEARCHER_SHORT[r] ?? r}</span>)}
                {p.questions.length > 0 && <span className="part-tag">{p.questions.length} question{p.questions.length > 1 ? "s" : ""}</span>}
                {p.affects.map((a) => <span key={a} className="tag">{a}</span>)}
              </div>
              {(p.note.trim() || p.parts.some((pt) => pt.note.trim())) && (
                <div className="note-peek">✎ {p.note.trim() || p.parts.find((pt) => pt.note.trim())?.note}</div>
              )}
            </button>
          ))}
          {!proposals.length && <p className="muted">The researchers made no proposals this time.</p>}
          {leftOut.length > 0 && (
            <details className="cut-list">
              <summary>Cut by the editor ({leftOut.length})</summary>
              <p className="hint">Duplicates and weaker ideas, left out so you have less to review.</p>
              {leftOut.map((p) => (
                <div key={p.id} className="cut-row">
                  <span className="tag">{RESEARCHER_SHORT[p.researcher] ?? p.researcher}</span>
                  {p.kind && <span className={`part-tag ${p.kind}`}>{p.kind}</span>}
                  <span className="grow">{p.title}</span>
                  {editable && (
                    <button className="small" onClick={() => onChange([...proposals, { ...p, decision: "pending" }])}>Bring back</button>
                  )}
                </div>
              ))}
            </details>
          )}
        </div>
      )}
    </div>
  );
}
