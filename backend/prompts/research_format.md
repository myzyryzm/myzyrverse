How to shape your output (it is returned as structured JSON):

- `background`: context the author needs to understand the material: facts, how things worked, what happened in an analogue. It is reference only and settles nothing about the story. A few sections, each with a clear `heading` and a `body` of short paragraphs or `- ` bullets.
- `proposals`: ideas for THIS story that the author can accept, keep as a maybe, or reject one at a time. At most 3: your strongest, not everything you thought of. An editor will cut weak and repeated ideas before the author sees them. Each proposal is ONE idea of ONE kind:
  - `title`: a short name for the idea.
  - `kind`: `characterization` (who someone is and why they act), `plot` (what happens) or `world` (setting, institutions, customs).
  - `text`: the idea itself in a few sentences. Stay inside its kind. Do not explain a trait with an invented plot event, and do not derive a plot event from a trait. If an idea seems to need both, propose only the stronger half.
  - `canon_fit`: one or two sentences on how it fits existing canon, planned events and timelines, and what it would change. Use "" if there is nothing to say.
  - `affects`: the characters, factions, places or events it touches.
  - `refs`: the source numbers the idea relies on.
  - `questions`: at most 2 questions this proposal itself raises and the author would need to decide. Do not repeat the open questions already in canon. Use [] if there are none.
- `sources`: every source you relied on, numbered from 1, with a `title` and a `url` (or a local filename for the author's notes).
- Citations: mark claims with the source number in square brackets, like `[2]` or `[1, 3]`, and list those numbers in `refs`. Never put URLs, titles or parenthetical citations in the text.
- Keep background and proposals apart: no story suggestions in background, no long history lessons in proposals.
