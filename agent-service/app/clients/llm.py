import json
from typing import Dict, List, Optional, Tuple

import requests

from app.utils.logging import get_logger


logger = get_logger()


class LLMClient:
    def __init__(
        self,
        name: str,
        provider: str,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 20,
    ):
        self.name = name
        self.provider = provider.lower()
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _allows_empty_key(self) -> bool:
        if self.provider not in ("openai", "openrouter"):
            return False
        return self.base_url.startswith(
            ("http://localhost", "http://127.0.0.1", "http://host.docker.internal")
        )

    def _flatten_messages(self, messages: List[Dict[str, str]]) -> Tuple[str, List[Dict[str, str]]]:
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        system_prompt = "\n".join(system_parts)
        non_system = [m for m in messages if m.get("role") != "system"]
        return system_prompt, non_system

    def _chat_openai_compatible(self, messages: List[Dict[str, str]], temperature: float) -> Optional[str]:
        payload = {"model": self.model, "messages": messages, "temperature": temperature}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        res = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        if res.status_code >= 400:
            logger.warning("[%s] LLM error: %s %s", self.name, res.status_code, res.text)
            return None
        data = res.json()
        return data["choices"][0]["message"]["content"]

    def _chat_gemini(self, messages: List[Dict[str, str]], temperature: float) -> Optional[str]:
        system_prompt, non_system = self._flatten_messages(messages)
        if not non_system:
            return None
        prompt_parts = []
        if system_prompt:
            prompt_parts.append(system_prompt)
        prompt_parts.extend([m.get("content", "") for m in non_system])
        text = "\n".join(prompt_parts).strip()
        payload = {
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {"temperature": temperature},
        }
        endpoint = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        res = requests.post(endpoint, json=payload, timeout=self.timeout)
        if res.status_code >= 400:
            logger.warning("[%s] Gemini error: %s %s", self.name, res.status_code, res.text)
            return None
        data = res.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def _chat_claude(self, messages: List[Dict[str, str]], temperature: float) -> Optional[str]:
        system_prompt, non_system = self._flatten_messages(messages)
        payload = {
            "model": self.model,
            "max_tokens": 512,
            "temperature": temperature,
            "messages": [{"role": m["role"], "content": m["content"]} for m in non_system],
        }
        if system_prompt:
            payload["system"] = system_prompt
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        res = requests.post(
            f"{self.base_url}/messages",
            headers=headers,
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        if res.status_code >= 400:
            logger.warning("[%s] Claude error: %s %s", self.name, res.status_code, res.text)
            return None
        data = res.json()
        return data["content"][0]["text"]

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> Optional[str]:
        if not self.api_key and not self._allows_empty_key():
            return None
        try:
            if self.provider in ("openai", "openrouter"):
                return self._chat_openai_compatible(messages, temperature)
            if self.provider == "gemini":
                return self._chat_gemini(messages, temperature)
            if self.provider == "claude":
                return self._chat_claude(messages, temperature)
            logger.warning("[%s] Unknown provider: %s", self.name, self.provider)
            return None
        except Exception as exc:
            logger.warning("[%s] LLM exception: %s", self.name, exc)
            return None

