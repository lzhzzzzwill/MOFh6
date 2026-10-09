"""Local stdio MCP adapter for the existing MOFh6 application.

Run this file with the Python environment used by MOFh6. The legacy code runs
in a child process so its print statements cannot corrupt MCP's stdout stream.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

try:
    # MCP Python SDK 2.x
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:
    # MCP Python SDK 1.x, which is present in some existing project environments.
    from mcp.server.fastmcp import FastMCP as MCPServer
    from mcp.server.fastmcp.exceptions import ToolError


PROJECT_DIR = Path(__file__).resolve().parent
WORKER = PROJECT_DIR / "mcp_worker.py"
TIMEOUT_SECONDS = int(os.environ.get("MOFH6_MCP_TIMEOUT_SECONDS", "1800"))
_single_flight = threading.Lock()
mcp = MCPServer("MOFh6")


def _invoke(operation: str, value: str) -> dict:
    """Execute one legacy operation and return its structured result."""
    if not value or not value.strip():
        raise ToolError("A non-empty input is required.")

    # Existing crawlers use shared relative paths and fixed output names.
    with _single_flight, tempfile.TemporaryDirectory(prefix="mofh6-mcp-") as temp_dir:
        result_path = Path(temp_dir) / "result.json"
        worker_env = os.environ.copy()
        # DOIRouter launches crawlers with the bare command "python". Keep it on
        # the same interpreter as this MCP server without editing legacy code.
        worker_env["PATH"] = os.pathsep.join(
            [str(Path(sys.executable).parent), worker_env.get("PATH", "")]
        )
        try:
            completed = subprocess.run(
                [sys.executable, str(WORKER), str(result_path)],
                input=json.dumps({"operation": operation, "value": value}, ensure_ascii=False),
                text=True,
                capture_output=True,
                cwd=PROJECT_DIR,
                env=worker_env,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(
                f"MOFh6 task exceeded {TIMEOUT_SECONDS} seconds."
            ) from exc

        if not result_path.exists():
            detail = (completed.stderr or completed.stdout).strip()[-4000:]
            raise ToolError(f"MOFh6 worker did not return a result: {detail}")

        result = json.loads(result_path.read_text(encoding="utf-8"))
        if completed.returncode != 0 or not result.get("ok"):
            detail = result.get("error") or completed.stderr.strip()[-4000:]
            raise ToolError(detail or "MOFh6 task failed.")
        return result["data"]


@mcp.tool()
def download_mof_paper(ccdc_code: str) -> dict:
    """Download a MOF paper and supporting files using a CCDC code in the local metadata."""
    return _invoke("download", ccdc_code)


@mcp.tool()
def process_mof_pdf(pdf_path: str) -> dict:
    """Extract and index a local PDF; pass an absolute path visible to this computer."""
    return _invoke("process_pdf", pdf_path)


@mcp.tool()
def run_mof_workflow(target: str) -> dict:
    """Run synthesis extraction for a CCDC code or an absolute local PDF path."""
    return _invoke("workflow", target)


@mcp.tool()
def ask_mof(question: str) -> dict:
    """Ask the existing MOFh6 query system a question, including its RAG or graph commands."""
    return _invoke("ask", question)


if __name__ == "__main__":
    mcp.run(transport="stdio")
