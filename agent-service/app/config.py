import os
import socket
from dataclasses import dataclass


def getenv(key: str, default: str = "") -> str:
    value = os.getenv(key, "").strip()
    return value if value else default


def load_env_file() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()
    except Exception:
        return


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
    llm_timeout: int
    chrome_mcp_url: str
    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str


def load_config() -> AppConfig:
    load_env_file()
    port = int(getenv("PORT", "5000"))
    eureka_server_url = getenv("EUREKA_SERVER_URL", "").rstrip("/")
    eureka_app_name = getenv("EUREKA_APP_NAME", "AGENT-SERVICE")
    instance_id = getenv("EUREKA_INSTANCE_ID", f"{eureka_app_name.lower()}:{local_ip()}:{port}")
    prefer_ip = getenv("PREFER_IP", "true").lower() == "true"
    llm_timeout = int(getenv("LLM_TIMEOUT", "20"))
    chrome_mcp_url = getenv("CHROME_MCP_URL", "http://localhost:8000/mcp")
    llm_provider = getenv("LLM_PROVIDER", "gemini")
    llm_base_url = getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
    llm_model = getenv("LLM_MODEL", "gemini-2.5-flash")
    llm_api_key = getenv("LLM_API_KEY", "")

    return AppConfig(
        port=port,
        eureka_server_url=eureka_server_url,
        eureka_app_name=eureka_app_name,
        eureka_instance_id=instance_id,
        prefer_ip=prefer_ip,
        llm_timeout=llm_timeout,
        chrome_mcp_url=chrome_mcp_url,
        llm_provider=llm_provider,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
    )

