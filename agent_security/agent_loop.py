import json
from contextlib import AsyncExitStack
from datetime import datetime

from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import stdio_client

from agent_security.mcp_launch import approval_server_params, filesystem_server_params
from agent_security.paths import ENV_PATH, LOG_DIR, TRACE_LOG
from agent_security.resolve_guard import execute_tool
from agent_security.toctou import after_tool

load_dotenv(ENV_PATH)
client = Anthropic()


def log_event(event: dict):
    event["timestamp"] = datetime.utcnow().isoformat()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRACE_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


def _claude_tools(tools):
    return [{
        "name": t.name,
        "description": t.description,
        "input_schema": t.input_schema
    } for t in tools]


async def run_agent(
    task_prompt: str, toctou=None, approval_tools=False, resolve_guard=None
):
    fs_params = filesystem_server_params()
    async with AsyncExitStack() as stack:
        fs_read, fs_write = await stack.enter_async_context(stdio_client(fs_params))
        fs_session = await stack.enter_async_context(ClientSession(fs_read, fs_write))
        await fs_session.initialize()
        sessions = {}
        fs_tools = (await fs_session.list_tools()).tools
        for tool in fs_tools:
            sessions[tool.name] = fs_session
        claude_tools = _claude_tools(fs_tools)

        if approval_tools:
            a_read, a_write = await stack.enter_async_context(
                stdio_client(approval_server_params())
            )
            a_session = await stack.enter_async_context(
                ClientSession(a_read, a_write)
            )
            await a_session.initialize()
            a_tools = (await a_session.list_tools()).tools
            for tool in a_tools:
                sessions[tool.name] = a_session
            claude_tools = claude_tools + _claude_tools(a_tools)

        messages = [{"role": "user", "content": task_prompt}]
        log_event({"type": "task_start", "prompt": task_prompt})
        hook_state = {"swapped": False}

        for _ in range(6):
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                tools=claude_tools,
                messages=messages
            )
            messages.append({"role": "assistant", "content": response.content})

            tool_calls = [b for b in response.content if b.type == "tool_use"]
            if not tool_calls:
                log_event({"type": "final_response", "content": str(response.content)})
                break

            tool_results = []
            for call in tool_calls:
                log_event({"type": "tool_call", "tool": call.name, "input": call.input})
                session = sessions.get(call.name, fs_session)
                result_text = await execute_tool(
                    session, call.name, call.input, resolve_guard, log_event
                )
                log_event({"type": "tool_result", "tool": call.name, "result": result_text})
                after_tool(toctou, call.name, call.input, hook_state, log_event)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": result_text
                })
            messages.append({"role": "user", "content": tool_results})
