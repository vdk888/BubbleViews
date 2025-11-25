"""
Agent Tool Definitions.

Defines OpenAI-format tool schemas for LLM function calling.
The agent uses these tools to extend its capabilities during response generation.

Available tools:
- fetch_url: Fetch and read content from web URLs
"""

from typing import Any, Dict, List


# Web Fetch Tool - allows agent to read content from URLs
WEB_FETCH_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "fetch_url",
        "description": (
            "Fetch and read the main text content from a web page. "
            "Use this when you need to reference information from a URL that was mentioned "
            "in the persona's background, writing rules, or the current Reddit thread. "
            "The tool extracts readable text, removing navigation, ads, and formatting. "
            "Content is truncated to ~2000 characters to fit context limits."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": (
                        "The full URL to fetch content from. "
                        "Must be a valid HTTP or HTTPS URL."
                    )
                }
            },
            "required": ["url"],
            "additionalProperties": False
        }
    }
}


# List of all available agent tools
AGENT_TOOLS: List[Dict[str, Any]] = [
    WEB_FETCH_TOOL,
]


def get_tool_by_name(name: str) -> Dict[str, Any] | None:
    """
    Get a tool definition by its name.

    Args:
        name: The tool name (e.g., "fetch_url")

    Returns:
        Tool definition dict or None if not found
    """
    for tool in AGENT_TOOLS:
        if tool.get("function", {}).get("name") == name:
            return tool
    return None


def get_tool_names() -> List[str]:
    """
    Get list of all available tool names.

    Returns:
        List of tool names
    """
    return [
        tool.get("function", {}).get("name")
        for tool in AGENT_TOOLS
        if tool.get("function", {}).get("name")
    ]
