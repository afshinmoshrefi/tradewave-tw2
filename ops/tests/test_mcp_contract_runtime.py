"""Feed the actual FastMCP-generated catalog into the public release validator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_candidate_server():
    """Load this checkout, even when the shared conftest adds /home/flask first."""
    path = ROOT / "mcpserver" / "server.py"
    spec = importlib.util.spec_from_file_location("release_candidate_mcpserver", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    assert Path(module.__file__).resolve() == path.resolve()
    return module


def _load_verifier():
    path = ROOT / "ops" / "verify_mcp_contract.py"
    spec = importlib.util.spec_from_file_location("verify_mcp_contract_runtime", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_actual_fastmcp_catalog_passes_release_contract_validator():
    server = _load_candidate_server()
    verifier = _load_verifier()
    published = []
    for tool in server.mcp._tool_manager.list_tools():
        annotations = tool.annotations.model_dump(by_alias=True, exclude_none=True)
        published.append(
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.parameters,
                "annotations": annotations,
            }
        )
    verifier.validate_tools(published)
