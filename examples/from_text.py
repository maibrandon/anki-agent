"""A local-file workflow over real MCP stdio. Preview first; --create asks approval."""
import argparse
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(args):
    text = args.file.read_text(encoding="utf-8")
    # Deterministic example: one Basic card per non-empty line. An AI client can
    # instead read this file and author better question/answer pairs.
    notes = [{"deck": args.deck, "note_type": "Basic", "fields": {"Front": f"Explain: {line.split('.')[0]}", "Back": line}, "tags": ["from_text"]}
             for line in text.splitlines() if line.strip()]
    async with stdio_client(StdioServerParameters(command=sys.executable, args=["-m", "anki_agent_mcp.server"], env=dict(os.environ))) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            preview = await session.call_tool("preview_notes", {"notes": notes})
            if preview.isError:
                raise RuntimeError(preview.content)
            data = preview.structuredContent or json.loads(preview.content[0].text)
            print(json.dumps(data, indent=2, ensure_ascii=False))
            if args.create and input("Create this batch? Type CREATE: ") == "CREATE":
                created = await session.call_tool("create_notes", {"preview_id": data["preview_id"]})
                if created.isError:
                    raise RuntimeError(created.content)
                print(json.dumps(created.structuredContent or json.loads(created.content[0].text), indent=2))


if __name__ == "__main__":
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--deck", default="Default")
    parser.add_argument("--create", action="store_true")
    asyncio.run(run(parser.parse_args()))
