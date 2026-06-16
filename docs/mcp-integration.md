# Model Context Protocol (MCP) Integration

OpsAgents exposes all 10 agents as tools under the Model Context Protocol (MCP), allowing them to run inside coding assistant agents like Claude Code, Cursor, and Antigravity.

## Launching the Server
By default, running `opsagents mcp` starts the stdio transport server. 

> [!NOTE]
> In the configurations below, make sure to replace `<absolute-path-to-repo>` with the actual absolute directory path where you cloned the repository (for example, `/home/techikrish/cloud-devops-agents`).

### Cursor Setup
1. Open Cursor Settings.
2. Under "Features" > "MCP", click "+ Add New MCP Server".
3. Configure the settings:
   - **Name**: `opsagents`
   - **Type**: `command`
   - **Command**: `<absolute-path-to-repo>/.venv/bin/opsagents mcp`

### Claude Code Setup
Add the server definition to your `.mcp.json` config:
```json
{
  "mcpServers": {
    "opsagents": {
      "command": "<absolute-path-to-repo>/.venv/bin/opsagents",
      "args": ["mcp"],
      "env": {
        "OPENAI_API_KEY": "your-key-here"
      }
    }
  }
}
```

## How Human-in-the-Loop Works in MCP
When an agent starts a plan that requires validation approval, the MCP tool returns a status block indicating `"paused_for_approval"` along with a unique `thread_id` and action details.

The coding agent presents the choice to the user and responds by calling `resume_agent(thread_id="...", approval_response="approve", agent_type="...")` to resume the graph run.
