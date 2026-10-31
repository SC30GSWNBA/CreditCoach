"""The CreditCoach agent: turns a user's question into a grounded answer.

Modules:
    pipeline  Question -> guardrail input rails -> retrieve corpus passages -> the chat model with the MCP tools and memory ->
              guardrail output rails -> cited explanation.
    mcp_host  Runs the model's tool calls on the CreditCoach MCP server for the signed-in user only.
"""
