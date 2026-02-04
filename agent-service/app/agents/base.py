from typing import Dict

from app.clients.llm import LLMClient


class BaseAgent:
    def __init__(self, name: str, llm: LLMClient):
        self.name = name
        self.llm = llm

    def run(self, context: Dict) -> Dict:
        raise NotImplementedError

