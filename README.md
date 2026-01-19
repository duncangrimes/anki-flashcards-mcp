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
| `add_notes` | Create flashcards in batch |
| `find_notes` | Search for notes using Anki query syntax |
| `get_notes_info` | Get detailed content for specific note IDs |
| `update_notes` | Update note properties (deck, fields, tags) while preserving review history |
| `delete_notes` | Delete notes by ID (use with `find_notes`) |
| `get_pdf_table_of_contents` | Extract PDF outline/chapters with page numbers |
| `read_pdf_pages` | Extract text from specific PDF pages |

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
- "Create flashcards for these 10 vocabulary words" → Uses `add_notes`
- "Make flashcards from chapter 5 of my textbook" → Uses `get_pdf_table_of_contents` + `read_pdf_pages` + `add_notes`
- "Delete all cards about mitosis from my Biology deck" → Uses `find_notes` + `delete_notes`

## License

MIT
