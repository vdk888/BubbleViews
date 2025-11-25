"""
Tool Executor for Agent Tool Calls.

Dispatches tool calls from LLM responses to appropriate service implementations.
Handles error recovery and result formatting for LLM consumption.
"""

import json
import logging
from typing import Any, Dict, List

from app.services.web_fetch import WebFetchService


logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""

    def __init__(self, tool_name: str, message: str, recoverable: bool = True):
        super().__init__(message)
        self.tool_name = tool_name
        self.message = message
        self.recoverable = recoverable


class ToolExecutor:
    """
    Executes tool calls from LLM responses.

    Dispatches tool calls to the appropriate service (e.g., WebFetchService)
    and formats results as JSON strings suitable for LLM consumption.

    Usage:
        executor = ToolExecutor(web_fetch=WebFetchService())
        result = await executor.execute("fetch_url", {"url": "https://example.com"})
    """

    def __init__(self, web_fetch: WebFetchService):
        """
        Initialize ToolExecutor with required services.

        Args:
            web_fetch: WebFetchService instance for URL fetching
        """
        self.web_fetch = web_fetch

        # Map tool names to handler methods
        self._handlers: Dict[str, Any] = {
            "fetch_url": self._execute_fetch_url,
        }

        logger.info(
            "ToolExecutor initialized",
            extra={"available_tools": list(self._handlers.keys())}
        )

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        correlation_id: str | None = None
    ) -> str:
        """
        Execute a tool call and return result as JSON string.

        Args:
            tool_name: Name of the tool to execute (e.g., "fetch_url")
            arguments: Dictionary of arguments for the tool
            correlation_id: Optional correlation ID for logging

        Returns:
            JSON string containing the tool result, suitable for LLM context

        Raises:
            ToolExecutionError: If tool is unknown or execution fails catastrophically
        """
        logger.info(
            f"Executing tool: {tool_name}",
            extra={
                "tool_name": tool_name,
                "arguments": arguments,
                "correlation_id": correlation_id,
            }
        )

        # Get handler for tool
        handler = self._handlers.get(tool_name)
        if not handler:
            error_msg = f"Unknown tool: {tool_name}"
            logger.error(error_msg, extra={"correlation_id": correlation_id})
            return json.dumps({
                "success": False,
                "error": error_msg,
                "tool": tool_name,
            })

        try:
            # Execute the tool
            result = await handler(arguments)

            logger.info(
                f"Tool execution successful: {tool_name}",
                extra={
                    "tool_name": tool_name,
                    "correlation_id": correlation_id,
                    "result_success": result.get("success", False),
                }
            )

            return json.dumps(result)

        except ToolExecutionError as e:
            logger.warning(
                f"Tool execution error: {tool_name} - {e.message}",
                extra={
                    "tool_name": tool_name,
                    "correlation_id": correlation_id,
                    "recoverable": e.recoverable,
                }
            )
            return json.dumps({
                "success": False,
                "error": e.message,
                "tool": tool_name,
                "recoverable": e.recoverable,
            })

        except Exception as e:
            logger.error(
                f"Unexpected tool execution error: {tool_name} - {e}",
                extra={"tool_name": tool_name, "correlation_id": correlation_id},
                exc_info=True
            )
            return json.dumps({
                "success": False,
                "error": f"Tool execution failed: {str(e)}",
                "tool": tool_name,
                "recoverable": False,
            })

    async def execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        correlation_id: str | None = None
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple tool calls and format results for LLM continuation.

        Args:
            tool_calls: List of tool call dicts from LLM response
                Each dict has: id, type, function: {name, arguments}
            correlation_id: Optional correlation ID for logging

        Returns:
            List of tool result dicts ready for LLM messages:
            [
                {
                    "tool_call_id": "call_abc123",
                    "role": "tool",
                    "content": "{...json result...}"
                },
                ...
            ]
        """
        results = []

        for call in tool_calls:
            call_id = call.get("id", "unknown")
            function_info = call.get("function", {})
            tool_name = function_info.get("name", "unknown")

            # Parse arguments (they come as JSON string from LLM)
            arguments_str = function_info.get("arguments", "{}")
            try:
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError as e:
                logger.warning(
                    f"Failed to parse tool arguments: {arguments_str}",
                    extra={"tool_name": tool_name, "correlation_id": correlation_id}
                )
                arguments = {}

            # Execute the tool
            result_json = await self.execute(
                tool_name=tool_name,
                arguments=arguments,
                correlation_id=correlation_id
            )

            results.append({
                "tool_call_id": call_id,
                "role": "tool",
                "content": result_json,
            })

        return results

    async def _execute_fetch_url(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute fetch_url tool.

        Args:
            arguments: Dict with 'url' key

        Returns:
            Fetch result dict
        """
        url = arguments.get("url")
        if not url:
            raise ToolExecutionError(
                tool_name="fetch_url",
                message="Missing required argument: url",
                recoverable=False
            )

        # Execute the fetch
        result = await self.web_fetch.fetch_url(url)

        # Format for LLM consumption
        if result["success"]:
            return {
                "success": True,
                "url": result["url"],
                "title": result.get("title"),
                "content": result["content"],
                "truncated": result.get("truncated", False),
            }
        else:
            return {
                "success": False,
                "url": result["url"],
                "error": result.get("error", "Unknown error"),
            }


def create_tool_executor() -> ToolExecutor:
    """
    Factory function to create a ToolExecutor with default services.

    Returns:
        Configured ToolExecutor instance
    """
    web_fetch = WebFetchService()
    return ToolExecutor(web_fetch=web_fetch)
