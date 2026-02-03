import logging
import os


REQUEST_ID_HEADER = "X-Request-ID"


def get_logger() -> logging.Logger:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    return logging.getLogger("agent-service")

