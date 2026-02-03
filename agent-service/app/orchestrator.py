import time
import uuid
from typing import Any, Callable, Dict, List

from app.agents.intake import IntakeAgent
from app.agents.recommend import RecommendationAgent
from app.agents.research import ResearchAgent
from app.clients.llm import LLMClient
from app.config import AppConfig
from app.tools.registry import ToolRegistry


class Orchestrator:
    def __init__(self, config: AppConfig, registry: ToolRegistry):
        self.registry = registry
        self.llm_clients = {
            "agent1": LLMClient(
                "agent1",
                config.agent_providers["agent1"],
                config.agent_keys["agent1"],
                config.agent_base_urls["agent1"],
                config.agent_models["agent1"],
            ),
            "agent2": LLMClient(
                "agent2",
                config.agent_providers["agent2"],
                config.agent_keys["agent2"],
                config.agent_base_urls["agent2"],
                config.agent_models["agent2"],
            ),
            "agent3": LLMClient(
                "agent3",
                config.agent_providers["agent3"],
                config.agent_keys["agent3"],
                config.agent_base_urls["agent3"],
                config.agent_models["agent3"],
            ),
        }
        self.agents = [
            IntakeAgent("intake", self.llm_clients["agent1"]),
            ResearchAgent("research", self.llm_clients["agent2"], registry),
            RecommendationAgent("recommend", self.llm_clients["agent3"]),
        ]

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        context: Dict[str, Any] = {"request": payload, "trace_id": str(uuid.uuid4()), "tool_calls": []}
        workflow = []
        for agent in self.agents:
            started = time.time()
            output = agent.run(context)
            context.update(output)
            workflow.append(
                {"agent": agent.name, "duration_ms": int((time.time() - started) * 1000)}
            )
        return {
            "trace_id": context["trace_id"],
            "normalized": context.get("normalized", {}),
            "plan": context.get("plan", []),
            "recommendations": context.get("recommendations", []),
            "tool_calls": context.get("tool_calls", []),
            "workflow": workflow,
            "llm_notes": context.get("llm_notes", []),
        }

    def run_with_stream(self, payload: Dict[str, Any], emit: Callable[[str, Dict[str, Any]], None]):
        context: Dict[str, Any] = {
            "request": payload,
            "trace_id": str(uuid.uuid4()),
            "tool_calls": [],
            "emit": emit,
        }
        workflow: List[Dict[str, Any]] = []
        for agent in self.agents:
            emit("agent_start", {"agent": agent.name})
            started = time.time()
            output = agent.run(context)
            context.update(output)
            duration_ms = int((time.time() - started) * 1000)
            workflow.append({"agent": agent.name, "duration_ms": duration_ms})
            emit("agent_done", {"agent": agent.name, "duration_ms": duration_ms})
        return {
            "trace_id": context.get("trace_id"),
            "normalized": context.get("normalized", {}),
            "plan": context.get("plan", []),
            "recommendations": context.get("recommendations", []),
            "tool_calls": context.get("tool_calls", []),
            "workflow": workflow,
            "llm_notes": context.get("llm_notes", []),
        }

