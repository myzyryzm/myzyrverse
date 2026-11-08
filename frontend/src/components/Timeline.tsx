import { useEffect, useState } from "react";
import { api } from "../api";
import type { TimelineItem } from "../types";
import { charHue } from "../util";

export function CharChip({ name, pov }: { name: string; pov?: boolean }) {
  const h = charHue(name);
  return (
    <span className={`chip${pov ? " pov" : ""}`}
          style={{ "--h": h } as React.CSSProperties} title={pov ? `${name} (POV)` : name}>
      {name}
    </span>
  );
}

export default function Timeline({ version, selected, onSelect }: {
  version: number; selected: string | null; onSelect: (id: string) => void;
}) {
  const [items, setItems] = useState<TimelineItem[]>([]);
  useEffect(() => {
    api.timeline().then(setItems).catch(() => setItems([]));
  }, [version]);

  if (!items.length) {
    return <div className="timeline empty">The timeline fills in as you create chapters. Each column shows the POV character on top and the significant characters below.</div>;
  }
  return (
    <div className="timeline">
      {items.map((it) => (
        <button key={it.run_id}
                className={`tl-col${selected === it.run_id ? " selected" : ""}${it.status === "draft" ? " draft" : ""}`}
                onClick={() => onSelect(it.run_id)} title={it.title}>
          <div className="tl-head">Ch {it.order}{it.status === "draft" ? " · draft" : ""}</div>
          <div className="tl-pov">{it.pov ? <CharChip name={it.pov} pov /> : <span className="muted">no POV</span>}</div>
          <div className="tl-chars">
            {it.characters_present.filter((c) => c !== it.pov).map((c) => <CharChip key={c} name={c} />)}
          </div>
        </button>
      ))}
    </div>
  );
}
