import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import ArcPlanner from "./components/ArcPlanner";
import Canon from "./components/Canon";
import Metrics from "./components/Metrics";
import ControlDeck from "./components/ControlDeck";
import Sandbox from "./components/Sandbox";
import Timeline from "./components/Timeline";
import type { AppConfig, NewRunPrefill, RunMeta, RunState } from "./types";
import { errMsg } from "./util";

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [runs, setRuns] = useState<RunMeta[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [runState, setRunState] = useState<RunState | null>(null);
  const [version, setVersion] = useState(0); // bump to make lore panels and timeline refetch
  const [prefill, setPrefill] = useState<NewRunPrefill | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [planner, setPlanner] = useState(false);
  const [metrics, setMetrics] = useState(false);
  const wasRunning = useRef(false);
  const gateEdits = useRef<() => Record<string, unknown>>(() => ({}));
  const registerEdits = useCallback((fn: () => Record<string, unknown>) => { gateEdits.current = fn; }, []);

  const bump = useCallback(() => setVersion((v) => v + 1), []);
  const notify = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 6000);
  }, []);

  useEffect(() => {
    api.config().then(setConfig).catch((e) => notify(errMsg(e)));
  }, [notify]);

  useEffect(() => {
    api.runs().then(setRuns).catch((e) => notify(errMsg(e)));
  }, [version, notify]);

  const refreshRun = useCallback(async () => {
    if (!selected) {
      setRunState(null);
      return;
    }
    try {
      const s = await api.runState(selected);
      setRunState(s);
      if (wasRunning.current && !s.running) bump(); // a phase just finished; lore may have changed
      wasRunning.current = s.running;
    } catch (e) {
      notify(errMsg(e));
    }
  }, [selected, bump, notify]);

  useEffect(() => {
    wasRunning.current = false;
    refreshRun();
  }, [selected, version, refreshRun]);

  useEffect(() => {
    if (!runState?.running) return;
    const t = window.setInterval(refreshRun, 1500);
    return () => window.clearInterval(t);
  }, [runState?.running, refreshRun]);

  const act = useCallback(
    async (fn: () => Promise<unknown>, after?: (r: unknown) => void) => {
      try {
        const r = await fn();
        after?.(r);
        wasRunning.current = true;
        bump();
      } catch (e) {
        notify(errMsg(e));
      }
    },
    [bump, notify],
  );

  return (
    <div className="app">
      <header className="topbar">
        <h1>Myzyrverse</h1>
        <span className="subtitle">Bronze Age Collapse · writing room</span>
        {config?.fake_llm && <span className="badge warn">FAKE_LLM: no Claude usage</span>}
        <button className="planner-link small" onClick={() => setPlanner(true)}>Arc planner</button>
        <button className="small" onClick={() => setMetrics(true)}>Metrics</button>
        <a className="manuscript-link" href="#" onClick={async (e) => {
          e.preventDefault();
          const m = await api.manuscript();
          const w = window.open("", "_blank");
          if (w) {
            w.document.title = "Manuscript";
            const pre = w.document.createElement("pre");
            pre.style.cssText = "white-space:pre-wrap;font:17px/1.6 Georgia,serif;max-width:46em;margin:2em auto;padding:0 16px";
            pre.textContent = m.text || "(no committed chapters yet)";
            w.document.body.appendChild(pre);
          }
        }}>Manuscript ↗</a>
      </header>

      <Timeline version={version} selected={selected} onSelect={setSelected} />

      <main className="columns">
        <section className="col canon">
          <Canon version={version} runs={runs} bump={bump} notify={notify} onOpenPlanner={() => setPlanner(true)}
                 onPlanArc={(ev) => setPrefill({ type: "plan_arc", target_event_id: ev.id, title: ev.title,
                                                 brief: `Plan the path to: ${ev.title}\n\n${ev.description}` })} />
        </section>
        <section className="col sandbox">
          <Sandbox key={selected ?? "none"} runState={runState} registerEdits={registerEdits} act={act} />
        </section>
        <section className="col deck">
          <ControlDeck config={config} runs={runs} selected={selected} onSelect={setSelected}
                       runState={runState} act={act} notify={notify} getEdits={() => gateEdits.current()}
                       prefill={prefill} clearPrefill={() => setPrefill(null)} />
        </section>
      </main>

      {planner && <ArcPlanner onClose={() => setPlanner(false)} bump={bump} notify={notify} />}
      {metrics && <Metrics onClose={() => setMetrics(false)} notify={notify} />}
      {toast && <div className="toast" onClick={() => setToast(null)}>{toast}</div>}
    </div>
  );
}
