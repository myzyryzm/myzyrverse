# Myzyrverse

A research + writing room for a historical-fantasy saga set around 1160 BCE during the Late Bronze Age collapse. It is an alternate history: the harem conspiracy against Ramesses III succeeds.

A LangGraph state machine runs researchers, an outliner, a writer and a critic. It pauses at human gates so you can edit everything before it moves on. Every LLM call goes through the Claude Agent SDK, which drives your local `claude` CLI, so usage bills to your Claude Code subscription, not an API key.

## Run it

```bash
# once
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..

# serve UI + API on http://localhost:8000
.venv/bin/uvicorn backend.app:app

# try the whole flow with canned output and zero Claude usage, in a scratch folder
FAKE_LLM=1 MYZYRVERSE_WORKSPACE=/tmp/myzyr-sandbox .venv/bin/uvicorn backend.app:app

# frontend dev with hot reload (proxies /api to :8000)
cd frontend && npm run dev     # http://localhost:5173

# tests (always fake LLM, temp dirs)
.venv/bin/python -m pytest
```

You must be logged in to Claude Code (`claude` works in your terminal). The runner removes `ANTHROPIC_API_KEY` from its environment so the CLI never silently switches to API billing.

## Run types

| Type | Pipeline | Use it for |
|---|---|---|
| Chapter | research → outline → prose + critique loop → ledger → commit | Writing a POV chapter |
| Research | research → ledger → commit | Lore questions, backstories, "how should the Sherden behave?" |
| Arc plan | research → arc plan → ledger → commit | Turning a big planned event into milestone sub-events |
| Lore | research → lore document → ledger → commit | Backstories, character and faction profiles, lore proposals you may adopt into prehistory |

Researchers run in parallel and are ticked per run. Ticking none skips research and its gate.

- **Antiquarian**: Bronze Age grounding. Weapons, dress, customs, bureaucracy, logistics.
- **Historian**: analogues from any era, such as the Praetorian Guard for the Sherden.
- **Mythographer**: analogues from fiction and myth, such as the Kingsguard. Always labeled as fiction.
- **Psychologist**: character wants, fears, competing obligations and friction.

Researchers can use web search and can read anything you drop in `lore/sources/` (notes, PDFs, articles).

Each researcher returns three things:

- **Background**: context to understand the material. It settles nothing about the story.
- **Proposals**: concrete story and lore ideas. Each has parts (characterization, plot, world, integration with canon) and any questions it raises.
- **Sources**: a numbered list. The text cites them only as superscript numbers, and they live on the **Sources** tab, numbered across the whole run.

## Gates

The graph pauses before each gate. The paused output appears in the center column, where you can edit it.

1. **Research review**: the Research tab switches between **Background** and **Proposals**. **Review proposals** opens a popup that steps through the proposals one at a time (arrows or ← →). On each one you can note any part, answer the questions it raises, add an overall note, and **Accept**, **Modify** (your notes say what to change) or **Reject**. Rejected proposals are removed from everything later agents see. Accepted and modified ones reach them as settled, together with your notes and answers. Proposals you leave unreviewed reach them as unreviewed ideas. Decisions are saved to `runs/<id>/proposals.json`. Below the research, write **your notes on the research** (answers, decisions, corrections). Your notes are editable at every later gate too, are saved to `runs/<id>/notes.md`, and are placed above every later agent's task as the highest-priority input.
2. **Outline review**: edit the beat sheet, the arc plan, or the lore document.
3. **Final prose review**: edit the chapter. The critic's notes are shown above it.
4. **Lore ledger review**: accept, edit, reject or add proposed lore changes, answers, questions and sub-events.

At any gate you can **Regenerate** that step with notes ("make beat 3 a betrayal"). At the prose gate this is **Force rewrite**: the writer revises the current draft against your notes. Resuming always reloads the canon, so lore edits you made while paused are picked up.

The critic loop is automatic. A failed draft goes back to the writer with the critique, up to 3 times (`MAX_REVISIONS`), then escalates to you.

## Lore model

```
lore/prehistory/*.md     your seed canon. Free-form markdown, any number of files. AI never writes here.
lore/open_questions.json things not yet settled. You add them; runs may answer them or raise new ones.
lore/events.json         where you want the story to go. Arcs (multi-chapter) and chapter events, with sub-events.
                         Each is a world event (Elam attacks Babylon) or a personal one (someone dies saving Aegon).
lore/timelines.json      the order each character lives through their events (edited in the Arc planner)
lore/sources/            reference material for the researchers
runs/<id>/ledger.json    what each committed run changed
runs/<id>/lore.md        a lore run's approved document
runs/<id>/notes.md       your notes on the research for that run
runs/<id>/proposals.json research proposals with your decisions, notes and answers
runs/<id>/sources.md     the run's numbered research sources
```

## Arc planner

**Arc planner** in the top bar opens a shared bank of events (world and personal) and one timeline per character: `Start → + → event → + → event → + → End`. Drag an event from the bank onto a `+`, or click a `+` to pick one or create a new one there. Being on a character's timeline means that character takes part. The **World** timeline orders world events.

There is no single global sequence to maintain. The **Story order** view derives it from all timelines together: an event comes after everything that precedes it on any character's timeline, and events with no constraint between them share a row. If two timelines contradict each other the view says which events could not be ordered. Events a character takes part in but that you haven't placed yet are listed under the timeline and don't affect the order. Agents see both the story order and every timeline.

A lore run's document is a proposal. From the ledger gate or after commit, **Adopt into prehistory** in the Lore doc tab appends it to a prehistory file you pick (or a new one). The AI still never writes prehistory on its own.

**Present** lore is never stored as one file. It is rebuilt by replaying the ledgers of committed runs in commit order, like replaying git commits. Reverting a run marks it reverted, so its lore changes, answers, new questions, event progress and prose all drop out together. Restoring brings them back.

Your manual edits to questions and events are stored as overrides and always win over what runs proposed. Manual present-lore notes can be attached to a run (reverted with it) or kept general.

## Layout

```
backend/
  graph.py         the StateGraph (read its docstring for the LangGraph concepts used)
  nodes/maestro.py deterministic router: decides the next node from state
  nodes/*.py       one file per node: researchers, weaver, loremaster, writer, grand_critic, archivist, gates, commit
  prompts/*.md     every system prompt. Edit these to tune voice and tone.
  runner.py        Claude Agent SDK wrapper (one function: run_agent)
  lore.py runs.py  files on disk, ledger replay, revert
  app.py           FastAPI endpoints, background graph runs
frontend/          Vite + React + TypeScript control deck
tests/             graph routing, lore ledger, HTTP end-to-end (fake LLM)
```

## Configuration

Per-node model and effort live in `backend/config.py`. The writer uses `claude-fable-5-1`; everything else uses `claude-opus-5-5`. Override any of them without code changes:

```bash
MODEL_WRITER=claude-opus-5-5 EFFORT_HISTORIAN=medium MAX_REVISIONS=2 .venv/bin/uvicorn backend.app:app
```

Checkpoints are in `data/checkpoints.sqlite`, one thread per run, so a paused run survives a server restart. The usage panel shows the API-equivalent cost the CLI reports for each node; on a subscription that is a measure of usage, not a bill.
