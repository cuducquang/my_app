import importlib.util
import os
from typing import List

from app.utils.logging import get_logger
from app.tools.registry import ToolRegistry


logger = get_logger()


def load_skill_plugins(registry: ToolRegistry, skills_dir: str) -> List[str]:
    loaded = []
    if not os.path.isdir(skills_dir):
        return loaded
    for filename in os.listdir(skills_dir):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        path = os.path.join(skills_dir, filename)
        module_name = f"skills_{filename[:-3]}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not spec.loader:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            if hasattr(module, "register_tools"):
                module.register_tools(registry)
                loaded.append(filename)
        except Exception as exc:
            logger.warning("skill plugin load failed: %s (%s)", filename, exc)
    return loaded

