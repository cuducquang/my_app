import time
import uuid
from typing import Any, Callable, Dict

from app.agents.single import SingleAgent
from app.clients.llm import LLMClient
from app.config import AppConfig
from app.tools.registry import ToolRegistry


class Orchestrator:
    def __init__(self, config: AppConfig, registry: ToolRegistry):
        self.registry = registry
        self.llm = LLMClient(
            "agent",
            config.llm_provider,
            config.llm_api_key,
            config.llm_base_url,
            config.llm_model,
            config.llm_timeout,
        )
        self.agent = SingleAgent("agent", self.llm, registry)

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        context: Dict[str, Any] = {"request": payload, "trace_id": str(uuid.uuid4()), "tool_calls": []}
        started = time.time()
        output = self.agent.run(context)
        context.update(output)
        duration_ms = int((time.time() - started) * 1000)
        return {
            "trace_id": context["trace_id"],
            "answer": context.get("answer", ""),
            "duration_ms": duration_ms,
        }

    def run_with_stream(self, payload: Dict[str, Any], emit: Callable[[str, Dict[str, Any]], None]):
        context: Dict[str, Any] = {
            "request": payload,
            "trace_id": str(uuid.uuid4()),
            "tool_calls": [],
            "emit": emit,
        }
        emit("agent_start", {"agent": self.agent.name})
        started = time.time()
        output = self.agent.run(context)
        context.update(output)
        duration_ms = int((time.time() - started) * 1000)
        emit("agent_done", {"agent": self.agent.name, "duration_ms": duration_ms})
        return {
            "trace_id": context.get("trace_id"),
            "answer": context.get("answer", ""),
            "duration_ms": duration_ms,
        }

