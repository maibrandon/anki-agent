"""Verify the open app via MCP; --write affects only the anki-agent deck."""
import argparse
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TARGET = "anki-agent"
QUERY = 'deck:"anki-agent" tag:anki-agent-test'


async def verify(write):
    async with stdio_client(StdioServerParameters(command=sys.executable, args=["-m", "anki_agent_mcp.server"], env=dict(os.environ))) as (read, output):
        async with ClientSession(read, output) as session:
            await session.initialize()
            async def call(name, arguments=None):
                result = await session.call_tool(name, arguments or {})
                if result.isError:
                    raise RuntimeError(result.content)
                return result.structuredContent or json.loads(result.content[0].text)
            status = await call("connection_status")
            if not status["collection_available"]:
                raise RuntimeError("Open your intended collection first.")
            before = await call("search_notes", {"query": QUERY, "limit": 10})
            summary = {"connected": True, "deck": TARGET, "existing_test_notes": before["total"]}
            if write:
                models = await call("list_note_types")
                by_name = {m["name"]: m for m in models["note_types"]}
                if not all(n in by_name and by_name[n]["supported"] for n in ("Basic", "Cloze")):
                    raise RuntimeError("This example needs stock Basic and Cloze note types.")
                deck = await call("create_deck", {"name": TARGET})
                summary["deck_id"] = deck["deck_id"]
                summary["deck_created"] = deck["created"]
                if before["total"] == 0:
                    basic_fields = dict(zip(by_name["Basic"]["fields"], ["Anki Agent: what protocol connects the agent to Anki?", "Model Context Protocol (MCP), through a local authenticated bridge."]))
                    cloze_fields = dict(zip(by_name["Cloze"]["fields"], ["Anki Agent uses {{c1::MCP}} while {{c2::Anki stays open}}.", "MVP connection test."]))
                    notes = [
                        {"deck": TARGET, "note_type": "Basic", "fields": basic_fields, "tags": ["anki-agent-test"]},
                        {"deck": TARGET, "note_type": "Cloze", "fields": cloze_fields, "tags": ["anki-agent-test"]},
                    ]
                    preview = await call("preview_notes", {"notes": notes})
                    unchanged = await call("search_notes", {"query": QUERY})
                    assert unchanged["total"] == 0, "Preview changed test-note count"
                    created = await call("create_notes", {"preview_id": preview["preview_id"]})
                    replay = await call("create_notes", {"preview_id": preview["preview_id"]})
                    assert replay["replayed"] and replay["created"] == 0
                    summary["created_test_notes"] = created["created"]
                    summary["retry_created"] = replay["created"]
                after = await call("search_notes", {"query": QUERY})
                summary["test_note_count"] = after["total"]
                summary["note_ids"] = [n["id"] for n in after["notes"]]
            print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Create the anki-agent deck and two tagged test notes if absent")
    asyncio.run(verify(parser.parse_args().write))
