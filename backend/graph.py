"""The graph.

    START -> maestro --(researchers, in parallel)--> join_research -> maestro
             maestro -> human_gate_research -> maestro          [pause before gate]
             maestro -> weaver -> maestro -> human_gate_outline -> maestro   [pause]
             maestro -> writer -> maestro -> grand_critic -> maestro
                        ^____ FAILED and revisions left ____|
             maestro -> human_gate_final -> maestro            [pause]
             maestro -> archivist -> maestro -> human_gate_ledger -> maestro [pause]
             maestro -> commit -> END

Research runs skip weaver/writer/critic; plan_arc runs use weaver in arc mode
and the outline gate for the plan; lore runs use the loremaster in place of the
weaver and the outline gate for the lore document.

LangGraph pieces used:
  * StateGraph + TypedDict: nodes return partial updates, merged per field.
  * Reducers: draft_history and usage use operator.add, so they append.
  * add_conditional_edges: the Maestro returns a node name or a list of names.
    A list fans out: all listed researchers run in the same superstep, and
    join_research (static edges from each) runs once after them.
  * interrupt_before + a checkpointer: the run pauses before each gate. State is
    saved after every node under thread_id = run id, so the UI can inspect it,
    edit it (aupdate_state) and resume (ainvoke(None)), even after a restart.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from . import config
from .nodes import archivist, commit, gates, grand_critic, loremaster, maestro, researchers, weaver, writer
from .state import RunState

GATES = ["human_gate_research", "human_gate_outline", "human_gate_final", "human_gate_ledger"]
WORKERS = ["weaver", "loremaster", "writer", "grand_critic", "archivist"]


def default_nodes() -> dict:
    nodes = {
        "maestro": maestro.maestro,
        "join_research": researchers.join_research,
        "weaver": weaver.weaver,
        "loremaster": loremaster.loremaster,
        "writer": writer.writer,
        "grand_critic": grand_critic.grand_critic,
        "archivist": archivist.archivist,
        "commit": commit.commit,
        "human_gate_research": gates.human_gate_research,
        "human_gate_outline": gates.human_gate_outline,
        "human_gate_final": gates.human_gate_final,
        "human_gate_ledger": gates.human_gate_ledger,
    }
    for name in config.RESEARCHERS:
        nodes[name] = researchers.make_researcher(name)
    return nodes


def build_graph(checkpointer: BaseCheckpointSaver | None, node_overrides: dict | None = None):
    nodes = {**default_nodes(), **(node_overrides or {})}
    builder = StateGraph(RunState)
    for name, fn in nodes.items():
        builder.add_node(name, fn)

    builder.add_edge(START, "maestro")
    targets = [*config.RESEARCHERS, *WORKERS, *GATES, "commit"]
    builder.add_conditional_edges("maestro", maestro.route, {**{t: t for t in targets}, maestro.END: END})

    for name in config.RESEARCHERS:
        builder.add_edge(name, "join_research")
    for name in ["join_research", *WORKERS, *GATES]:
        builder.add_edge(name, "maestro")
    builder.add_edge("commit", END)

    return builder.compile(checkpointer=checkpointer, interrupt_before=GATES)
