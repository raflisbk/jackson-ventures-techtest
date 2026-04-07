# Phase 7 — Summary: MCP Server

**Completed**: 2026-04-08
**Status**: ✅ DONE

## What Was Built

### `mcp_server/__init__.py`
Empty package marker.

### `mcp_server/server.py`
FastMCP 3.2.0 stdio server with 3 tools:

| Tool | Description |
|------|-------------|
| `list_industries` | Returns sorted list of distinct industry values in DB |
| `search_companies` | Filters by `industry` (case-insensitive exact) and/or `q` (substring), `limit` (max 100) |
| `get_company` | Returns full company dict by integer PK, or `None` |

Key safeguards:
- `logging.basicConfig(stream=sys.stderr)` on FIRST two lines — stdout clean (MCP-1)
- Separate `_engine` from `app/database.py` — no `Settings()` import → no `OPENAI_API_KEY` needed at startup
- `PRAGMA journal_mode=WAL` on `_engine` — concurrent reads with FastAPI (MCP-2)
- `from app.models import Company` inside each tool function — deferred import avoids Settings at module load
- `mcp.run(transport="stdio")` in `__main__`

### `app/database.py` — updated
- Added `PRAGMA journal_mode=WAL` immediately after `create_engine()` — FastAPI side of WAL pair

### `requirements.txt` — updated
- Added `fastmcp==3.2.0`

## Verification

```python
import asyncio, mcp_server.server as s
tools = asyncio.run(s.mcp.list_tools())
# → ['list_industries', 'search_companies', 'get_company'] ✓
```

Full test suite: 44/44 passed (zero regressions).

## Claude Desktop Config (for end-users)
```json
{
  "mcpServers": {
    "company-research": {
      "command": "python",
      "args": ["mcp_server/server.py"],
      "cwd": "/path/to/project"
    }
  }
}
```

## Requirements Satisfied

| Req | How |
|-----|-----|
| MCP-01 | `mcp.run(transport="stdio")` with FastMCP 3.2.0 |
| MCP-02 | `list_industries` returns distinct industry JSON array |
| MCP-03 | `search_companies(industry="FinTech")` filters correctly |
| MCP-2 (WAL) | Both `_engine` (MCP) and `engine` (FastAPI) use WAL PRAGMA |
