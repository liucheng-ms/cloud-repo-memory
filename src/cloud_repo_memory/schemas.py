"""Load self-contained tool schemas from the single packaged normative artifact."""

from copy import deepcopy
from importlib.resources import files
import json
from typing import Any

CONTRACT = json.loads(files("cloud_repo_memory.contracts").joinpath(
    "local-mvp-v1.schema.json").read_text(encoding="utf-8"))


def tool_schema(name: str) -> dict[str, Any]:
    # MCP schemas are standalone documents; preserve local refs and definitions.
    return {"$schema": CONTRACT["$schema"], **deepcopy(CONTRACT["$defs"][name]),
            "$defs": deepcopy(CONTRACT["$defs"])}
