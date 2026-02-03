import os
import socket
from dataclasses import dataclass
from typing import Dict


def getenv(key: str, default: str = "") -> str:
    value = os.getenv(key, "").strip()
    return value if value else default


def local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


@dataclass
class AppConfig:
    port: int
    eureka_server_url: str
    eureka_app_name: str
    eureka_instance_id: str
    prefer_ip: bool
    chrome_mcp_url: str
    chrome_mcp_tool: str
    agent_keys: Dict[str, str]
    agent_base_urls: Dict[str, str]
    agent_models: Dict[str, str]
    agent_providers: Dict[str, str]


def load_config() -> AppConfig:
    port = int(getenv("PORT", "5000"))
    eureka_server_url = getenv("EUREKA_SERVER_URL", "").rstrip("/")
    eureka_app_name = getenv("EUREKA_APP_NAME", "AGENT-SERVICE")
    instance_id = getenv("EUREKA_INSTANCE_ID", f"{eureka_app_name.lower()}:{local_ip()}:{port}")
    prefer_ip = getenv("PREFER_IP", "true").lower() == "true"
    chrome_mcp_url = getenv("CHROME_MCP_URL", "")
    chrome_mcp_tool = getenv("CHROME_MCP_TOOL", "browser.navigate")

    agent_keys = {
        "agent1": getenv("AGENT1", ""),
        "agent2": getenv("AGENT2", ""),
        "agent3": getenv("AGENT3", ""),
    }
    agent_base_urls = {
        "agent1": getenv("AGENT1_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"),
        "agent2": getenv("AGENT2_BASE_URL", "https://api.anthropic.com/v1"),
        "agent3": getenv("AGENT3_BASE_URL", "https://openrouter.ai/api/v1"),
    }
    agent_models = {
        "agent1": getenv("AGENT1_MODEL", "gemini-1.5-flash"),
        "agent2": getenv("AGENT2_MODEL", "claude-3-5-sonnet-20241022"),
        "agent3": getenv("AGENT3_MODEL", "openai/gpt-4o-mini"),
    }
    agent_providers = {
        "agent1": getenv("AGENT1_PROVIDER", "gemini"),
        "agent2": getenv("AGENT2_PROVIDER", "claude"),
        "agent3": getenv("AGENT3_PROVIDER", "openrouter"),
    }

    return AppConfig(
        port=port,
        eureka_server_url=eureka_server_url,
        eureka_app_name=eureka_app_name,
        eureka_instance_id=instance_id,
        prefer_ip=prefer_ip,
        chrome_mcp_url=chrome_mcp_url,
        chrome_mcp_tool=chrome_mcp_tool,
        agent_keys=agent_keys,
        agent_base_urls=agent_base_urls,
        agent_models=agent_models,
        agent_providers=agent_providers,
    )

