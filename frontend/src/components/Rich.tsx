import { useContext, useState, type ReactNode } from "react";
import type { OpenQuestion, ResearchSource } from "../types";
import { QuestionsContext, questionIdPattern } from "../questions";

interface RichProps {
  text: string;
  sources?: ResearchSource[];
  /** Called when a superscript reference is clicked. Without it, a reference links straight to its URL. */
  onRef?: (n: number) => void;
}

const INLINE = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|\[\d+(?:\s*,\s*\d+)*\])/g;

/**
 * A deliberately small markdown subset for research text: paragraphs, "- " lists, **bold**, *italic*.
 * Reference markers like [2] or [1, 3] become superscripts. Known open-question ids show the question on hover.
 */
export default function Rich({ text, sources, onRef }: RichProps) {
  const questions = useContext(QuestionsContext);
  const qre = questionIdPattern(questions);
  const inline = (t: string) => inlineTokens(t, sources, onRef, (s, key) => withQuestions(s, key, qre, questions));
  const blocks = (text || "").trim().split(/\n\s*\n/).filter((b) => b.trim());
  return (
    <div className="rich">
      {blocks.map((block, bi) => {
        const lines = block.split("\n").filter((l) => l.trim());
        const out: ReactNode[] = [];
        let list: string[] = [];
        let para: string[] = [];
        const flushList = () => {
          if (list.length) out.push(<ul key={`u${out.length}`}>{list.map((l, i) => <li key={i}>{inline(l)}</li>)}</ul>);
          list = [];
        };
        const flushPara = () => {
          if (para.length) out.push(<p key={`p${out.length}`}>{inline(para.join(" "))}</p>);
          para = [];
        };
        for (const line of lines) {
          const item = line.match(/^\s*[-*]\s+(.*)$/);
          const head = line.match(/^\s*#{1,6}\s+(.*)$/);
          if (item) { flushPara(); list.push(item[1]); }
          else if (head) { flushPara(); flushList(); out.push(<p key={`h${out.length}`} className="rich-head">{inline(head[1])}</p>); }
          else { flushList(); para.push(line.trim()); }
        }
        flushPara();
        flushList();
        return <div key={bi}>{out}</div>;
      })}
    </div>
  );
}

function inlineTokens(text: string, sources: ResearchSource[] | undefined, onRef: RichProps["onRef"],
                      plain: (s: string, key: number) => ReactNode): ReactNode[] {
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
    return plain(tok, i);
  });
}

function withQuestions(text: string, key: number, re: RegExp | null, questions: Map<string, OpenQuestion>): ReactNode {
  if (!re) return <span key={key}>{text}</span>;
  // split() with one capture group puts the matched ids at the odd indexes.
  const bits = text.split(re);
  if (bits.length === 1) return <span key={key}>{text}</span>;
  return (
    <span key={key}>
      {bits.map((b, j) => {
        const q = j % 2 ? questions.get(b) : undefined;
        return q ? <QRef key={j} q={q} /> : b;
      })}
    </span>
  );
}

/** A question id with a popover of the question. Fixed positioning, so scrolling panels and modals don't clip it. */
export function QRef({ q }: { q: OpenQuestion }) {
  const [at, setAt] = useState<{ x: number; y: number; below: boolean } | null>(null);
  const show = (el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    const below = r.top < 160;
    setAt({ x: Math.min(Math.max(r.left, 8), window.innerWidth - 368), y: below ? r.bottom + 6 : r.top - 6, below });
  };
  const answered = q.status !== "open" && !!q.answer?.trim();
  return (
    <span className="qref" tabIndex={0}
          onMouseEnter={(e) => show(e.currentTarget)} onMouseLeave={() => setAt(null)}
          onFocus={(e) => show(e.currentTarget)} onBlur={() => setAt(null)}>
      {q.id}
      {at && (
        <span className={`qref-tip${at.below ? " below" : ""}`} role="tooltip" style={{ left: at.x, top: at.y }}>
          {q.about && <span className="qref-about">{q.about}</span>}
          <span className="qref-q">{q.question}</span>
          {answered
            ? <span className="qref-answer"><b>Answered:</b> {q.answer}</span>
            : <span className="qref-status">{q.status}</span>}
        </span>
      )}
    </span>
  );
}
