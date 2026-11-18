import { createContext, useEffect, useState } from "react";
import { api } from "./api";
import type { OpenQuestion } from "./types";

export type QuestionMap = Map<string, OpenQuestion>;

/** Open questions by id, so text that quotes an id (e.g. "q-8518cf12") can show the question. */
export const QuestionsContext = createContext<QuestionMap>(new Map());

/** Load the effective open questions. A failed load leaves the map empty: ids then render as plain text. */
export function useQuestionMap(deps: unknown[]): QuestionMap {
  const [map, setMap] = useState<QuestionMap>(() => new Map());
  useEffect(() => {
    let live = true;
    api.questions()
      .then((qs) => { if (live) setMap(new Map(qs.map((q) => [q.id, q]))); })
      .catch(() => { /* keep whatever we had */ });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return map;
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const cache = new WeakMap<QuestionMap, RegExp | null>();

/**
 * A regex matching any known question id as a whole token, with one capture group so String.split keeps the ids.
 * Run-created questions keep ledger ids like "lore-purple-guild-17", so this matches the known ids rather than a q- pattern.
 */
export function questionIdPattern(map: QuestionMap): RegExp | null {
  if (cache.has(map)) return cache.get(map)!;
  const ids = [...map.keys()].filter(Boolean).sort((a, b) => b.length - a.length);
  const re = ids.length ? new RegExp(`(?<![\\w-])(${ids.map(escape).join("|")})(?![\\w-])`) : null;
  cache.set(map, re);
  return re;
}
