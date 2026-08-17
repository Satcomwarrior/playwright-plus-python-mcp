from __future__ import annotations

import asyncio
import base64
import json

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from .agent_runtime import BrowserSessionManager, BrowserSettings, list_downloads

server = Server("persistent-computer-agent")
manager = BrowserSessionManager(BrowserSettings.from_env())


def _json(data) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="computer_start",
            description="Start or resume the persistent browser computer. Uses a persistent Chrome profile by default or attaches to an existing Chrome session over CDP when configured.",
            inputSchema={"type": "object", "properties": {"url": {"type": "string"}}},
        ),
        types.Tool(name="computer_status", description="Get current computer/browser status and handoff information.", inputSchema={"type": "object", "properties": {}}),
        types.Tool(name="computer_navigate", description="Navigate the persistent browser to a URL.", inputSchema={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}),
        types.Tool(name="computer_text", description="Read visible text from the current browser page.", inputSchema={"type": "object", "properties": {"limit": {"type": "integer", "default": 20000}}}),
        types.Tool(name="computer_screenshot", description="Take a screenshot of the current browser page.", inputSchema={"type": "object", "properties": {"full_page": {"type": "boolean", "default": True}}}),
        types.Tool(name="computer_click", description="Click a page element by CSS selector.", inputSchema={"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}),
        types.Tool(name="computer_click_text", description="Click the first visible element containing the supplied text.", inputSchema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}),
        types.Tool(name="computer_fill", description="Fill a form field identified by CSS selector.", inputSchema={"type": "object", "properties": {"selector": {"type": "string"}, "value": {"type": "string"}}, "required": ["selector", "value"]}),
        types.Tool(
            name="computer_download",
            description="Click an attachment or download link and save the downloaded file into the agent download directory.",
            inputSchema={"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}, "timeout_ms": {"type": "integer", "default": 30000}}},
        ),
        types.Tool(name="computer_list_downloads", description="List files downloaded by the persistent browser computer, newest first.", inputSchema={"type": "object", "properties": {"limit": {"type": "integer", "default": 20}}}),
        types.Tool(name="computer_handoff", description="Return the live handoff target for user authentication or other manual interaction, then preserve the same browser session for the agent to resume.", inputSchema={"type": "object", "properties": {}}),
        types.Tool(name="computer_close", description="Close the persistent browser computer cleanly.", inputSchema={"type": "object", "properties": {}}),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None):
    args = arguments or {}
    if name == "computer_start":
        return _json(await manager.start(args.get("url")))
    if name == "computer_status":
        return _json(await manager.status())
    if name == "computer_navigate":
        return _json(await manager.navigate(args["url"]))
    if name == "computer_text":
        return [types.TextContent(type="text", text=await manager.visible_text(int(args.get("limit", 20000))))]
    if name == "computer_screenshot":
        image = await manager.screenshot(bool(args.get("full_page", True)))
        return [types.ImageContent(type="image", data=base64.b64encode(image).decode("ascii"), mimeType="image/png")]
    if name == "computer_click":
        return _json(await manager.click(args["selector"]))
    if name == "computer_click_text":
        return _json(await manager.click_text(args["text"]))
    if name == "computer_fill":
        return _json(await manager.fill(args["selector"], args["value"]))
    if name == "computer_download":
        return _json(await manager.click_and_download(selector=args.get("selector"), text=args.get("text"), timeout_ms=int(args.get("timeout_ms", 30000))))
    if name == "computer_list_downloads":
        return _json(list_downloads(manager.settings.download_dir, int(args.get("limit", 20))))
    if name == "computer_handoff":
        return _json(await manager.status())
    if name == "computer_close":
        await manager.close()
        return _json({"closed": True})
    raise ValueError(f"Unknown tool: {name}")


async def _main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="persistent-computer-agent",
                server_version="0.2.0",
                capabilities=server.get_capabilities(notification_options=NotificationOptions(), experimental_capabilities={}),
            ),
        )


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
