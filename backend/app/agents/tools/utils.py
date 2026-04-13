"""Common utilities for ADK agent tools."""

from google.adk.tools import ToolContext


def get_user_id(tool_context: ToolContext, fallback: str = "default_user") -> str:
    """Lấy user_id từ tool context.

    Ưu tiên: state["user_id"] > fallback.
    Chỉ có 1 nơi để thay đổi logic nếu cần.
    """
    return tool_context.state.get("user_id", fallback)
