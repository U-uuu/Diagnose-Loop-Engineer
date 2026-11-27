"""编译并运行诊断工作流。"""

from langgraph.graph import END, START, StateGraph

from autoloop.graph.nodes import DiagnosisNodes, guarded
from autoloop.graph.state import DiagnosisState
from autoloop.schemas.diagnosis import DiagnosisStatus


def _next(state: DiagnosisState) -> str:
    return "stop" if state["status"] == DiagnosisStatus.FAILED else "continue"


def run_workflow(nodes: DiagnosisNodes, initial: DiagnosisState) -> DiagnosisState:
    steps = (
        nodes.load_incident, nodes.build_context, nodes.diagnose, nodes.validate_diagnosis,
        nodes.plan_repair, nodes.validate_plan, nodes.save_result,
    )
    graph = StateGraph(DiagnosisState)
    for step in steps:
        graph.add_node(step.__name__, guarded(step))
    graph.add_edge(START, steps[0].__name__)
    for current, following in zip(steps, steps[1:]):
        graph.add_conditional_edges(
            current.__name__, _next, {"stop": END, "continue": following.__name__},
        )
    graph.add_edge(steps[-1].__name__, END)
    return graph.compile().invoke(initial)
