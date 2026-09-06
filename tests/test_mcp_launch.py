from agent_security.mcp_launch import (
    FILESYSTEM_PACKAGE,
    approval_server_params,
    filesystem_server_params,
    mcp_child_env,
)
from agent_security.paths import REPO_ROOT, SANDBOX_DIR


def test_child_env_drops_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-key")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = mcp_child_env({"PYTHONPATH": "/app"})
    assert "ANTHROPIC_API_KEY" not in env
    assert env["PATH"] == "/usr/bin"
    assert env["PYTHONPATH"] == "/app"


def test_filesystem_params_use_npx_on_host(monkeypatch):
    monkeypatch.delenv("MCP_FILESYSTEM_BIN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-key")
    params = filesystem_server_params()
    assert params.command == "npx"
    assert params.args == ["-y", FILESYSTEM_PACKAGE, str(SANDBOX_DIR)]
    assert params.env is not None
    assert "ANTHROPIC_API_KEY" not in params.env


def test_filesystem_params_use_baked_bin(monkeypatch):
    monkeypatch.setenv("MCP_FILESYSTEM_BIN", "/usr/local/bin/mcp-server-filesystem")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-key")
    params = filesystem_server_params()
    assert params.command == "/usr/local/bin/mcp-server-filesystem"
    assert params.args == [str(SANDBOX_DIR)]
    assert params.env is not None
    assert "ANTHROPIC_API_KEY" not in params.env


def test_approval_params_drop_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-key")
    params = approval_server_params()
    assert params.args == ["-m", "agent_security.approval_mcp"]
    assert params.cwd == str(REPO_ROOT)
    assert params.env is not None
    assert params.env["PYTHONPATH"] == str(REPO_ROOT)
    assert "ANTHROPIC_API_KEY" not in params.env
