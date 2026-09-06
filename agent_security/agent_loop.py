import json
from datetime import datetime

from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent_security.paths import ENV_PATH, LOG_DIR, SANDBOX_DIR, TRACE_LOG
from agent_security.toctou import after_tool

load_dotenv(ENV_PATH)
client = Anthropic()


def log_event(event: dict):
    event["timestamp"] = datetime.utcnow().isoformat()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRACE_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


async def run_agent(task_prompt: str, toctou=None):
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", str(SANDBOX_DIR)]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools

            claude_tools = [{
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema
            } for t in mcp_tools]

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
                    result = await session.call_tool(call.name, call.input)
                    result_text = str(result.content)
                    log_event({"type": "tool_result", "tool": call.name, "result": result_text})
                    after_tool(toctou, call.name, call.input, hook_state, log_event)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": result_text
                    })
                messages.append({"role": "user", "content": tool_results})
