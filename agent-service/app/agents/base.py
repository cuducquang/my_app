from typing import Dict

from app.clients.llm import LLMClient


class BaseAgent:
    def __init__(self, name: str, llm: LLMClient):
        self.name = name
        self.llm = llm

    def run(self, context: Dict) -> Dict:
        raise NotImplementedError

    def _add_llm_note(self, context: Dict, prompt: str) -> None:
        response = self.llm.chat(
            [
                {"role": "system", "content": "You are a travel assistant."},
                {"role": "user", "content": prompt},
            ]
        )
        if response:
            context.setdefault("llm_notes", []).append({"agent": self.name, "note": response})
            emit = context.get("emit")
            if callable(emit):
                emit("agent_note", {"agent": self.name, "note": response})

