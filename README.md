# Anki Flashcards MCP Server

An MCP (Model Context Protocol) server that enables LLMs like Claude or Cursor to interact with your Anki flashcard collection via [AnkiConnect](https://github.com/FooSoft/anki-connect).

## Features

| Tool | Description |
|------|-------------|
| `ping` | Health check - verify Anki and AnkiConnect are running |
| `get_deck_names` | List all your Anki decks (returns dict with `count`) |
| `create_deck` | Create new decks (supports nested decks with `::`) |
| `delete_deck` | Delete a deck and optionally all its cards |
| `get_model_names` | List available Note Types (e.g., Basic, Cloze) |
| `get_model_field_names` | Get field names for a Note Type (e.g., Front/Back) |
| **`add_notes`** | **Efficiently create multiple flashcards in one batch (Preferred)** |
| `add_note` | Create a single flashcard |
| `find_notes` | Search for notes using Anki query syntax |
| `get_notes_info` | Get detailed content for specific note IDs |

## Prerequisites

1. **Anki** - [Download](https://apps.ankiweb.net/) and install
2. **AnkiConnect** - Install the add-on in Anki:
   - Open Anki → Tools → Add-ons → Get Add-ons
   - Enter code: `2055492159`
   - Restart Anki
3. **Python 3.10+**
4. **uv** (recommended) - [Install uv](https://docs.astral.sh/uv/getting-started/installation/)

## Installation

```bash
# Clone the repository
git clone https://github.com/duncangrimes/anki-flashcards-mcp.git
cd anki-flashcards-mcp

# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

## Configuration

Add the server to your MCP client configuration:

**Cursor**: Settings → Features → MCP Servers → Add new MCP server  
**Claude Desktop**: Edit config file (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "anki": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/anki-flashcards-mcp",
        "run",
        "anki-mcp"
      ]
    }
  }
}
```

**Important**: Replace `/path/to/anki-flashcards-mcp` with the actual path to your cloned repository.

## Usage

Once configured, you can ask your LLM to:

- "Check if Anki is running" → Uses `ping`
- "What decks do I have?" → Uses `get_deck_names`
- "Find all notes tagged 'biology'" → Uses `find_notes`
- "Delete my 'Test' deck" → Uses `delete_deck`
- "Create flashcards for these 10 vocabulary words" → Uses `add_notes` (Batch)

### Example Workflow (Batching)

When you provide multiple items, the LLM will automatically use `add_notes` for efficiency:

```
User: "Create flashcards for French fruits: apple=pomme, orange=orange, banana=banane"

LLM Workflow:
1. ping() -> OK
2. get_deck_names() -> {"decks": ["Default"], "count": 1}
3. create_deck("French Vocabulary") -> 123456789
4. get_model_field_names("Basic") -> {"fields": ["Front", "Back"], ...}
5. add_notes([
     {"deck_name": "French Vocabulary", "model_name": "Basic", "fields": {"Front": "apple", "Back": "pomme"}},
     {"deck_name": "French Vocabulary", "model_name": "Basic", "fields": {"Front": "orange", "Back": "orange"}},
     {"deck_name": "French Vocabulary", "model_name": "Basic", "fields": {"Front": "banana", "Back": "banane"}}
   ]) -> {"success_count": 3, "failure_count": 0}
```

## Efficiency & Performance

- **Batching**: Use `add_notes` instead of `add_note` whenever creating multiple cards. This significantly reduces network overhead and latency.
- **Structured Data**: All list-returning tools (like `get_deck_names`) return a dictionary wrapper (e.g., `{"decks": [...], "count": 5}`). This ensures proper serialization across the MCP protocol and provides helpful metadata.
- **Timeout**: The server is configured with a 120-second timeout to handle large Anki collections or slow database operations.

## Troubleshooting

### "Could not connect to Anki"
- Ensure Anki is running.
- Verify AnkiConnect is installed.
- Check that nothing else is using port 8765.

### "Aborted" or Timeout errors
- Large collections can be slow. The server now supports a 120s timeout. If you still see issues, check Anki's performance or try smaller batches.

## License

MIT
