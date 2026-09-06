from typing import Literal

from mcp.server.mcpserver import MCPServer

from agent_security.approval import issue_token, log_approval_event, run_action

server = MCPServer("approval")


@server.tool(structured_output=False)
def issue_approval(action: Literal["publish_note", "payout"]) -> str:
    """Issue a one-time approval token for an action."""
    return issue_token(action, log=log_approval_event)


@server.tool(structured_output=False)
def execute(action: Literal["publish_note", "payout"], token: str) -> str:
    """Execute an action using an approval token."""
    return run_action(action, token, log=log_approval_event)


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
