import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import ClientSession
from mcp.client.stdio import stdio_client

from agent_security.mcp_launch import filesystem_server_params


async def main():
    server_params = filesystem_server_params()
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for tool in tools.tools:
                print(tool.name, "-", tool.description)


if __name__ == "__main__":
    asyncio.run(main())
