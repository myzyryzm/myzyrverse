import type { ReactNode } from "react";
import type { ResearchSource } from "../types";

interface RichProps {
  text: string;
  sources?: ResearchSource[];
  /** Called when a superscript reference is clicked. Without it, a reference links straight to its URL. */
  onRef?: (n: number) => void;
}

const INLINE = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|\[\d+(?:\s*,\s*\d+)*\])/g;

/**
 * A deliberately small markdown subset for research text: paragraphs, "- " lists, **bold**, *italic*.
 * Reference markers like [2] or [1, 3] become superscripts.
 */
export default function Rich({ text, sources, onRef }: RichProps) {
  const blocks = (text || "").trim().split(/\n\s*\n/).filter((b) => b.trim());
  return (
    <div className="rich">
      {blocks.map((block, bi) => {
        const lines = block.split("\n").filter((l) => l.trim());
        const out: ReactNode[] = [];
        let list: string[] = [];
        let para: string[] = [];
        const flushList = () => {
          if (list.length) out.push(<ul key={`u${out.length}`}>{list.map((l, i) => <li key={i}>{inline(l, sources, onRef)}</li>)}</ul>);
          list = [];
        };
        const flushPara = () => {
          if (para.length) out.push(<p key={`p${out.length}`}>{inline(para.join(" "), sources, onRef)}</p>);
          para = [];
        };
        for (const line of lines) {
          const item = line.match(/^\s*[-*]\s+(.*)$/);
          const head = line.match(/^\s*#{1,6}\s+(.*)$/);
          if (item) { flushPara(); list.push(item[1]); }
          else if (head) { flushPara(); flushList(); out.push(<p key={`h${out.length}`} className="rich-head">{inline(head[1], sources, onRef)}</p>); }
          else { flushList(); para.push(line.trim()); }
        }
        flushPara();
        flushList();
        return <div key={bi}>{out}</div>;
      })}
    </div>
  );
}

function inline(text: string, sources: ResearchSource[] | undefined, onRef: RichProps["onRef"]): ReactNode[] {
  return text.split(INLINE).filter(Boolean).map((tok, i) => {
    if (tok.startsWith("**") && tok.endsWith("**")) return <strong key={i}>{tok.slice(2, -2)}</strong>;
    const ref = tok.match(/^\[(\d+(?:\s*,\s*\d+)*)\]$/);
    if (ref) {
      const nums = ref[1].split(",").map((x) => Number(x.trim()));
      return (
        <sup key={i} className="ref">
          {nums.map((n, j) => {
            const src = sources?.find((s) => s.n === n);
            const sep = j < nums.length - 1 ? "," : "";
            if (onRef) {
              return <span key={n}><a href={`#src-${n}`} title={src?.title}
                                      onClick={(e) => { e.preventDefault(); onRef(n); }}>{n}</a>{sep}</span>;
            }
            return <span key={n}><a href={src?.url || undefined} target="_blank" rel="noreferrer" title={src?.title}>{n}</a>{sep}</span>;
          })}
        </sup>
      );
    }
    if (tok.length > 2 && tok.startsWith("*") && tok.endsWith("*")) return <em key={i}>{tok.slice(1, -1)}</em>;
    return <span key={i}>{tok}</span>;
  });
}
