import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { CallRollup, DecisionCounts, KeepCounts, MetricsView, RunMetrics } from "../types";
import { RUN_TYPE_LABELS, errMsg } from "../util";

interface Props {
  onClose: () => void;
  notify: (m: string) => void;
}

const DOC_LABELS: Record<string, string> = {
  lore_doc: "Lore doc (Loremaster)",
  arc_plan: "Arc plan (Weaver)",
  chapter_outline: "Chapter outline (Weaver)",
};

const KIND_LABELS: Record<string, string> = {
  lore: "Lore facts", new_question: "Open questions", hook: "Hooks", answer: "Answers",
  event_update: "Event updates", sub_event: "Sub-events",
};

// ---------------- formatting ----------------

const DASH = "—";
const num = (n: number | null | undefined) => (n == null ? DASH : n.toLocaleString());
const usd = (n: number | null | undefined) => (n == null ? DASH : `$${n.toFixed(n >= 100 ? 0 : 2)}`);
const pct = (part: number, whole: number) => (whole ? `${Math.round((100 * part) / whole)}%` : DASH);

function compact(n: number | null | undefined): string {
  if (n == null) return DASH;
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e4) return `${Math.round(n / 1e3)}k`;
  return n.toLocaleString();
}

function dur(ms: number | null | undefined): string {
  if (ms == null) return DASH;
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ${m % 60}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

const tokensIn = (u: CallRollup) =>
  u.input == null && u.cache_read == null && u.cache_write == null
    ? null : (u.input ?? 0) + (u.cache_read ?? 0) + (u.cache_write ?? 0);

// ---------------- small pieces ----------------

/** One thin stacked bar. Steps are an ordered one-hue ramp (strongest = best outcome), so they
 *  read without color vision; every count is also printed beside the bar. */
function Split({ parts, label }: { parts: { name: string; n: number; step: 1 | 2 | 3 }[]; label: string }) {
  const total = parts.reduce((a, p) => a + p.n, 0);
  return (
    <div className="split" role="img" aria-label={`${label}: ${parts.map((p) => `${p.n} ${p.name}`).join(", ")}`}>
      {total === 0 ? <span className="split-empty" /> : parts.filter((p) => p.n > 0).map((p) => (
        <span key={p.name} className={`split-seg s${p.step}`} style={{ flexGrow: p.n }}
              title={`${p.name}: ${p.n} (${pct(p.n, total)})`} />
      ))}
    </div>
  );
}

function decisionParts(c: DecisionCounts) {
  return [
    { name: "accepted", n: c.accepted ?? 0, step: 1 as const },
    { name: "maybe", n: c.maybe ?? 0, step: 2 as const },
    { name: "rejected", n: c.rejected ?? 0, step: 3 as const },
  ];
}

function keepParts(c: KeepCounts) {
  return [{ name: "kept", n: c.kept, step: 1 as const }, { name: "dropped", n: c.dropped, step: 3 as const }];
}

function Legend({ items }: { items: [string, 1 | 2 | 3][] }) {
  return (
    <div className="split-legend">
      {items.map(([name, step]) => (
        <span key={name}><i className={`split-key s${step}`} />{name}</span>
      ))}
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function DecisionRow({ name, c }: { name: string; c: DecisionCounts }) {
  const total = (c.accepted ?? 0) + (c.maybe ?? 0) + (c.rejected ?? 0);
  return (
    <tr>
      <td>{name}</td>
      <td className="bar-cell"><Split parts={decisionParts(c)} label={name} /></td>
      <td className="num">{num(c.accepted ?? 0)}</td>
      <td className="num">{num(c.maybe ?? 0)}</td>
      <td className="num">{num(c.rejected ?? 0)}</td>
      <td className="num strong">{pct(c.accepted ?? 0, total)}</td>
    </tr>
  );
}

function KeepRow({ name, c }: { name: string; c: KeepCounts }) {
  return (
    <tr>
      <td>{name}</td>
      <td className="bar-cell"><Split parts={keepParts(c)} label={name} /></td>
      <td className="num">{num(c.kept)}</td>
      <td className="num">{num(c.dropped)}</td>
      <td className="num strong">{pct(c.kept, c.kept + c.dropped)}</td>
    </tr>
  );
}

function UsageTable({ rows, keyLabel }: { rows: (CallRollup & { label: string; sub?: string })[]; keyLabel: string }) {
  return (
    <table className="mtable">
      <thead>
        <tr>
          <th>{keyLabel}</th><th className="num">Calls</th><th className="num">Cost</th><th className="num">Time</th>
          <th className="num">Turns</th><th className="num">Tokens in</th><th className="num">Tokens out</th>
          <th className="num">Searches</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label + (r.sub ?? "")}>
            <td>{r.label}{r.sub && <span className="muted small-text"> · {r.sub}</span>}</td>
            <td className="num">{num(r.calls)}</td>
            <td className="num">{usd(r.cost_usd)}</td>
            <td className="num">{dur(r.duration_ms)}</td>
            <td className="num">{num(r.num_turns)}</td>
            <td className="num" title={r.input == null ? undefined
              : `uncached ${num(r.input)} · cache read ${num(r.cache_read)} · cache write ${num(r.cache_write)}`}>
              {compact(tokensIn(r))}
            </td>
            <td className="num">{compact(r.output)}</td>
            <td className="num">{num(r.web_searches)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------- per-run detail ----------------

function editText(e: { edited: boolean | null; similarity: number | null; chars_before: number | null; chars_after: number | null }) {
  if (e.edited == null) return DASH;
  if (!e.edited) return "approved as written";
  const delta = (e.chars_after ?? 0) - (e.chars_before ?? 0);
  const same = Math.min(99, Math.floor((e.similarity ?? 0) * 100)); // an edit is never "100% unchanged"
  return `edited by hand (${delta >= 0 ? "+" : "−"}${Math.abs(delta).toLocaleString()} chars, ${same}% unchanged)`;
}

function RunDetail({ r }: { r: RunMetrics }) {
  return (
    <div className="run-detail">
      {r.backfilled && (
        <p className="hint">Partial data: this run predates metrics. Cost, per-call time and decisions were recovered;
          tokens, active time, regenerations and edits were never recorded.</p>
      )}
      <div className="detail-grid">
        <div>
          <h4>Time</h4>
          <dl className="kv">
            <dt>Active (agents working)</dt><dd>{dur(r.time.active_ms)}</dd>
            <dt>Waiting on your review</dt><dd>{dur(r.time.waiting_ms)}</dd>
            <dt>Elapsed</dt><dd>{dur(r.time.elapsed_ms)}</dd>
          </dl>
        </div>
        {r.research && (
          <div>
            <h4>Research review</h4>
            <Split parts={decisionParts(r.research)} label="Research decisions" />
            <p className="small-text">
              {r.research.accepted} accepted ({r.research.accepted_with_notes} with notes), {r.research.maybe} maybe,{" "}
              {r.research.rejected} rejected
              {r.research.cut_by_editor ? ` · ${r.research.cut_by_editor} cut by the editor` : ""}
              {r.research_regenerations ? ` · regenerated ${r.research_regenerations}×` : ""}
            </p>
          </div>
        )}
        {r.doc && (
          <div>
            <h4>{DOC_LABELS[r.doc.doc] ?? r.doc.doc}</h4>
            <p className="small-text">
              Regenerated {r.doc.regenerations}× · {r.doc.approved ? editText(r.doc) : "not yet approved"}
            </p>
          </div>
        )}
        {r.prose && (
          <div>
            <h4>Prose review</h4>
            <p className="small-text">
              Critic: {r.prose.critic.map((c) => `${c.verdict === "PASSED" ? "pass" : "fail"}${c.score ? ` ${c.score}/10` : ""}`).join(" → ") || DASH}
              <br />Force rewrites {r.prose.force_rewrites} · {r.prose.approved ? editText(r.prose) : "not yet approved"}
            </p>
          </div>
        )}
        {r.ledger && (
          <div>
            <h4>Lore ledger review</h4>
            <Split parts={keepParts(r.ledger)} label="Ledger rows" />
            <p className="small-text">
              {r.ledger.kept} kept, {r.ledger.dropped} dropped
              {r.ledger.added_by_user ? ` · ${r.ledger.added_by_user} added by you` : ""}
              {r.ledger.answered ? ` · ${r.ledger.answered} questions answered` : ""}
            </p>
          </div>
        )}
      </div>
      {r.nodes.length > 0 && (
        <UsageTable keyLabel="Node" rows={r.nodes.map((n) => ({ ...n, label: n.node, sub: n.model }))} />
      )}
    </div>
  );
}

// ---------------- the modal ----------------

export default function Metrics({ onClose, notify }: Props) {
  const [data, setData] = useState<MetricsView | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [by, setBy] = useState<"node" | "model">("node");

  const load = useCallback(() => {
    api.metrics().then(setData).catch((e) => notify(errMsg(e)));
  }, [notify]);
  useEffect(load, [load]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", h);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", h);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const t = data?.totals;
  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Metrics">
        <div className="modal-head">
          <h2>Metrics</h2>
          <span className="hint">Cost is the API-equivalent figure the Claude CLI reports, not a bill.</span>
          <button className="small" onClick={load}>Refresh</button>
          <button className="ghost" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {!t || !data ? <p className="hint metrics-body">Loading…</p> : (
          <div className="metrics-body">
            <div className="stats">
              <Stat label="Cost" value={usd(t.usage.cost_usd)} sub={`${t.runs} runs · ${num(t.usage.calls)} agent calls`} />
              <Stat label="Active time" value={dur(t.time.active_ms)} sub={`waiting on review ${dur(t.time.waiting_ms)}`} />
              <Stat label="Tokens in" value={compact(tokensIn(t.usage))}
                    sub={t.usage.input == null ? undefined : `${compact(t.usage.cache_read)} from cache`} />
              <Stat label="Tokens out" value={compact(t.usage.output)} />
              <Stat label="Web searches" value={num(t.usage.web_searches)} />
              <Stat label="Agent turns" value={num(t.usage.num_turns)} />
            </div>
            {t.partial_runs > 0 && (
              <p className="hint">
                {t.partial_runs} of {t.runs} runs predate metrics, so their tokens, active time, regenerations and
                edits are missing from these totals. A dash means no data, not zero.
              </p>
            )}

            <div className="metrics-grid">
              <section className="mpanel">
                <h3>Research review</h3>
                {t.research.total === 0 ? <p className="hint">No research reviews yet.</p> : (
                  <>
                    <Legend items={[["accepted", 1], ["maybe", 2], ["rejected", 3]]} />
                    <table className="mtable">
                      <thead>
                        <tr><th /><th /><th className="num">Acc.</th><th className="num">Maybe</th>
                          <th className="num">Rej.</th><th className="num">Rate</th></tr>
                      </thead>
                      <tbody>
                        <DecisionRow name="All proposals" c={t.research} />
                        {Object.entries(t.research.by_researcher).sort().map(([k, c]) => <DecisionRow key={k} name={k} c={c} />)}
                      </tbody>
                    </table>
                    {Object.keys(t.research.by_kind).length > 0 && (
                      <table className="mtable">
                        <thead><tr><th>By kind</th><th /><th className="num">Acc.</th><th className="num">Maybe</th>
                          <th className="num">Rej.</th><th className="num">Rate</th></tr></thead>
                        <tbody>
                          {Object.entries(t.research.by_kind).sort().map(([k, c]) => <DecisionRow key={k} name={k} c={c} />)}
                        </tbody>
                      </table>
                    )}
                    <p className="small-text muted">
                      {t.research.total} proposals over {t.research.runs} reviews · {t.research.accepted_with_notes} accepted
                      with notes · {t.research.cut_by_editor} cut by the editor · {t.research.regenerations} regenerations
                    </p>
                  </>
                )}
              </section>

              <section className="mpanel">
                <h3>Loremaster review</h3>
                {t.docs.length === 0 && t.ledger.runs === 0 ? <p className="hint">No synthesis or ledger reviews yet.</p> : (
                  <>
                    {t.docs.length > 0 && (
                      <table className="mtable">
                        <thead><tr><th>Document</th><th className="num">Runs</th><th className="num">Regenerated</th>
                          <th className="num">Edited by hand</th></tr></thead>
                        <tbody>
                          {t.docs.map((d) => (
                            <tr key={d.doc}>
                              <td>{DOC_LABELS[d.doc] ?? d.doc}</td>
                              <td className="num">{d.runs}</td>
                              <td className="num">{d.regenerations}×</td>
                              <td className="num">{d.edited} of {d.approved} ({pct(d.edited, d.approved)})</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                    {t.ledger.runs > 0 && (
                      <>
                        <Legend items={[["kept", 1], ["dropped", 3]]} />
                        <table className="mtable">
                          <thead><tr><th>Ledger rows</th><th /><th className="num">Kept</th><th className="num">Dropped</th>
                            <th className="num">Rate</th></tr></thead>
                          <tbody>
                            <KeepRow name="All rows" c={t.ledger} />
                            {Object.entries(t.ledger.by_kind).sort().map(([k, c]) => <KeepRow key={k} name={KIND_LABELS[k] ?? k} c={c} />)}
                          </tbody>
                        </table>
                        <p className="small-text muted">
                          {t.ledger.runs} ledger reviews · {t.ledger.added_by_user} rows added by you ·{" "}
                          {t.ledger.answered} questions answered · {t.ledger.regenerations} regenerations
                        </p>
                      </>
                    )}
                  </>
                )}
              </section>

              <section className="mpanel">
                <h3>Prose review</h3>
                {t.prose.runs === 0 ? <p className="hint">No chapter has reached the critic yet.</p> : (
                  <>
                    <Legend items={[["passed", 1], ["failed", 3]]} />
                    <Split label="Critic verdicts" parts={[{ name: "passed", n: t.prose.passed, step: 1 },
                                                           { name: "failed", n: t.prose.failed, step: 3 }]} />
                    <dl className="kv">
                      <dt>Critic pass rate</dt><dd>{pct(t.prose.passed, t.prose.critic_rounds)} of {t.prose.critic_rounds} rounds</dd>
                      <dt>Average critic score</dt><dd>{t.prose.avg_score == null ? DASH : `${t.prose.avg_score}/10`}</dd>
                      <dt>Automatic revisions</dt><dd>{t.prose.failed}</dd>
                      <dt>Your force rewrites</dt><dd>{t.prose.force_rewrites}</dd>
                      <dt>Approved</dt><dd>{t.prose.approved} of {t.prose.runs} chapters</dd>
                      <dt>Edited by hand</dt><dd>{t.prose.edited} of {t.prose.approved} ({pct(t.prose.edited, t.prose.approved)})</dd>
                    </dl>
                  </>
                )}
              </section>

              <section className="mpanel">
                <div className="mpanel-head">
                  <h3>Spend by {by}</h3>
                  <div className="seg-toggle">
                    <button className={by === "node" ? "on" : ""} onClick={() => setBy("node")}>Node</button>
                    <button className={by === "model" ? "on" : ""} onClick={() => setBy("model")}>Model</button>
                  </div>
                </div>
                <UsageTable keyLabel={by === "node" ? "Node" : "Model"}
                            rows={by === "node" ? t.nodes.map((n) => ({ ...n, label: n.node }))
                                                : t.models.map((m) => ({ ...m, label: m.model }))} />
              </section>
            </div>

            <section className="mpanel">
              <h3>Runs</h3>
              <table className="mtable runs-table">
                <thead>
                  <tr><th>Run</th><th>Type</th><th>Status</th><th className="num">Cost</th><th className="num">Active</th>
                    <th className="num">Tokens in</th><th className="num">Accepted</th><th className="num">Ledger kept</th></tr>
                </thead>
                <tbody>
                  {data.runs.map((r) => (
                    <Fragment key={r.id}>
                      <tr className={`run-row${open === r.id ? " open" : ""}`} tabIndex={0}
                          onClick={() => setOpen(open === r.id ? null : r.id)}
                          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(open === r.id ? null : r.id); } }}>
                        <td>
                          <span className="caret">{open === r.id ? "▾" : "▸"}</span> {r.title}
                          {r.backfilled && <span className="badge">partial</span>}
                          {r.running && <span className="badge running">running</span>}
                        </td>
                        <td>{RUN_TYPE_LABELS[r.type] ?? r.type}</td>
                        <td>{r.status}</td>
                        <td className="num">{usd(r.usage.cost_usd)}</td>
                        <td className="num">{dur(r.time.active_ms)}</td>
                        <td className="num">{compact(tokensIn(r.usage))}</td>
                        <td className="num">{r.research ? `${r.research.accepted}/${r.research.total} (${pct(r.research.accepted, r.research.total)})` : DASH}</td>
                        <td className="num">{r.ledger ? `${r.ledger.kept}/${r.ledger.kept + r.ledger.dropped}` : DASH}</td>
                      </tr>
                      {open === r.id && (
                        <tr className="run-detail-row"><td colSpan={8}><RunDetail r={r} /></td></tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
