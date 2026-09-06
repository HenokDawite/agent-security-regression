import os
import sys

from mcp import StdioServerParameters

from agent_security.paths import REPO_ROOT, SANDBOX_DIR

FILESYSTEM_PACKAGE = "@modelcontextprotocol/server-filesystem"


def mcp_child_env(extra=None):
    """Environment for MCP subprocesses, without the Anthropic API key."""
    env = {key: value for key, value in os.environ.items() if key != "ANTHROPIC_API_KEY"}
    if extra:
        env.update(extra)
    return env


def filesystem_server_params():
    baked = os.environ.get("MCP_FILESYSTEM_BIN")
    if baked:
        return StdioServerParameters(
            command=baked,
            args=[str(SANDBOX_DIR)],
            env=mcp_child_env(),
            cwd=str(REPO_ROOT),
        )
    return StdioServerParameters(
        command="npx",
        args=["-y", FILESYSTEM_PACKAGE, str(SANDBOX_DIR)],
        env=mcp_child_env(),
        cwd=str(REPO_ROOT),
    )


def approval_server_params():
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "agent_security.approval_mcp"],
        env=mcp_child_env({"PYTHONPATH": str(REPO_ROOT)}),
        cwd=str(REPO_ROOT),
    )
