"""
Anki MCP Server - Connect LLMs to Anki via AnkiConnect.

This MCP server provides tools for LLMs to interact with a user's Anki
flashcard collection. It enables reading deck structures, note types,
and creating new flashcards programmatically.

Prerequisites:
    - Anki must be running
    - AnkiConnect add-on must be installed (code: 2055492159)
"""

import httpx
from mcp.server.fastmcp import FastMCP
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anki-mcp")

# Initialize FastMCP server
mcp = FastMCP("AnkiConnect")

ANKI_CONNECT_URL = "http://localhost:8765"

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    """Get or create a persistent httpx.AsyncClient."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=120.0)
    return _client


async def invoke_anki(action: str, version: int = 6, **params):
    """
    Helper function to communicate with AnkiConnect.
    
    Args:
        action: The AnkiConnect action to invoke.
        version: API version (default 6).
        **params: Additional parameters for the action.
        
    Returns:
        The result from AnkiConnect.
        
    Raises:
        Exception: If Anki is not running or AnkiConnect returns an error.
    """
    payload = {
        "action": action,
        "version": version,
        "params": params
    }
    logger.info(f"Invoking Anki: {action} with params: {params}")
    try:
        client = await get_client()
        response = await client.post(ANKI_CONNECT_URL, json=payload)
        response.raise_for_status()
        result = response.json()
        
        if result.get("error"):
            logger.error(f"AnkiConnect returned error for '{action}': {result['error']}")
            raise Exception(result["error"])
        
        return result.get("result")
    except httpx.TimeoutException:
        logger.error(f"Timeout while invoking Anki action '{action}'")
        raise Exception(f"AnkiConnect timed out after 120 seconds during '{action}'")
    except httpx.ConnectError:
        raise Exception(
            "Could not connect to Anki. Please ensure:\n"
            "1. Anki is currently running\n"
            "2. The AnkiConnect add-on is installed (code: 2055492159)\n"
            "3. Anki is configured to allow connections (default in AnkiConnect)"
        )
    except Exception as e:
        logger.error(f"AnkiConnect error during '{action}': {e}")
        raise


# =============================================================================
# Health Check Tool
# =============================================================================

@mcp.tool()
async def ping() -> dict:
    """
    Check if Anki is running and AnkiConnect is responsive.
    
    Use this tool first to verify the connection before performing other operations.
    
    Returns:
        A dictionary with connection status and AnkiConnect version.
        
    Example:
        >>> ping()
        {"status": "ok", "version": 6}
    """
    try:
        version = await invoke_anki("version")
        return {"status": "ok", "version": version}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# =============================================================================
# Deck Tools
# =============================================================================

@mcp.tool()
async def get_deck_names() -> dict:
    """
    Get a list of all existing deck names in Anki.
    
    Use this tool to discover what decks the user has before creating new ones
    or adding cards. Deck names use "::" as a separator for nested decks
    (e.g., "Languages::French::Vocabulary").
    
    Returns:
        A dictionary with "decks" (list of deck names) and "count".
        
    Example:
        >>> get_deck_names()
        {"decks": ["Default", "Languages::French", "Languages::Spanish"], "count": 3}
    """
    decks = await invoke_anki("deckNames")
    return {"decks": decks, "count": len(decks)}


@mcp.tool()
async def create_deck(deck: str) -> int:
    """
    Create a new deck in Anki.
    
    Use "::" to create nested/hierarchical decks (e.g., "Science::Biology::Cells").
    If the deck already exists, this is a no-op and returns the existing deck ID.
    
    Args:
        deck: The name of the deck to create.
        
    Returns:
        The deck ID (integer).
        
    Example:
        >>> create_deck("French Vocabulary")
        1234567890123
    """
    return await invoke_anki("createDeck", deck=deck)


@mcp.tool()
async def delete_deck(deck: str, cards_too: bool = True) -> None:
    """
    Delete a deck in Anki.
    
    Args:
        deck: The name of the deck to delete.
        cards_too: If True (default), delete all cards and notes in the deck.
                   If False, move cards to the "Default" deck instead.
    """
    return await invoke_anki("deleteDecks", decks=[deck], cardsToo=cards_too)


# =============================================================================
# Model (Note Type) Tools
# =============================================================================

@mcp.tool()
async def get_model_names() -> dict:
    """
    Get a list of all available Note Types (models) in Anki.
    
    Note Types define the structure of flashcards (what fields they have).
    Common built-in types include:
    - "Basic": Has "Front" and "Back" fields
    - "Basic (and reversed card)": Creates two cards from one note
    - "Cloze": For fill-in-the-blank style cards with "Text" and "Extra" fields
    
    Use this tool to discover available models before adding notes.
    
    Returns:
        A dictionary with "models" (list of Note Type names) and "count".
        
    Example:
        >>> get_model_names()
        {"models": ["Basic", "Basic (and reversed card)", "Cloze"], "count": 3}
    """
    models = await invoke_anki("modelNames")
    return {"models": models, "count": len(models)}


@mcp.tool()
async def get_model_field_names(model_name: str) -> dict:
    """
    Get the field names for a specific Note Type (model).
    
    IMPORTANT: Always call this before add_note to know the exact field names
    required. Different models have different fields:
    - "Basic" model: ["Front", "Back"]
    - "Cloze" model: ["Text", "Extra"]
    
    Args:
        model_name: The name of the Note Type to inspect.
        
    Returns:
        A dictionary with "model_name", "fields" (list of field names), and "count".
        
    Example:
        >>> get_model_field_names("Basic")
        {"model_name": "Basic", "fields": ["Front", "Back"], "count": 2}
        
        >>> get_model_field_names("Cloze")
        {"model_name": "Cloze", "fields": ["Text", "Extra"], "count": 2}
    """
    fields = await invoke_anki("modelFieldNames", modelName=model_name)
    return {"model_name": model_name, "fields": fields, "count": len(fields)}


# =============================================================================
# Note (Card) Tools
# =============================================================================

@mcp.tool()
async def add_note(
    deck_name: str,
    model_name: str,
    fields: dict,
    tags: list[str] | None = None
) -> int:
    """
    Add a new note (flashcard) to Anki.
    
    Before calling this tool:
    1. Use get_deck_names() to verify the deck exists (or create_deck() to make it)
    2. Use get_model_names() to find available Note Types
    3. Use get_model_field_names() to get the exact field names for your chosen model
    
    Args:
        deck_name: The name of the deck to add the note to.
        model_name: The name of the Note Type (e.g., "Basic", "Cloze").
        fields: A dictionary mapping field names to content.
                For "Basic": {"Front": "question", "Back": "answer"}
                For "Cloze": {"Text": "{{c1::answer}} is hidden", "Extra": "hint"}
        tags: Optional list of tags for organization (e.g., ["vocabulary", "chapter1"]).
        
    Returns:
        The note ID (integer) if successful.
        
    Raises:
        Exception: If the note is a duplicate (duplicates are blocked by default).
        
    Example:
        >>> add_note(
        ...     deck_name="French Vocabulary",
        ...     model_name="Basic",
        ...     fields={"Front": "Apple", "Back": "Pomme"},
        ...     tags=["fruit", "food"]
        ... )
        1234567890123
    """
    note = {
        "deckName": deck_name,
        "modelName": model_name,
        "fields": fields,
        "tags": tags or [],
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck"
        }
    }
    return await invoke_anki("addNote", note=note)


@mcp.tool()
async def add_notes(notes: list[dict]) -> dict:
    """
    Add multiple notes (flashcards) to Anki in a single batch.
    
    This is much more efficient than calling add_note multiple times.
    
    Args:
        notes: A list of note dictionaries. Each dictionary should contain:
               - deck_name: str
               - model_name: str
               - fields: dict
               - tags: list[str] (optional)
        
    Returns:
        A dictionary with "note_ids" (list of IDs or None for failures),
        "success_count", and "failure_count".
        
    Example:
        >>> add_notes([
        ...     {"deck_name": "Decks::Default", "model_name": "Basic", "fields": {"Front": "A", "Back": "B"}},
        ...     {"deck_name": "Decks::Default", "model_name": "Basic", "fields": {"Front": "C", "Back": "D"}}
        ... ])
        {"note_ids": [1234567890, 1234567891], "success_count": 2, "failure_count": 0}
    """
    anki_notes = []
    for n in notes:
        anki_notes.append({
            "deckName": n["deck_name"],
            "modelName": n["model_name"],
            "fields": n["fields"],
            "tags": n.get("tags", []),
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck"
            }
        })
    note_ids = await invoke_anki("addNotes", notes=anki_notes)
    success_count = sum(1 for nid in note_ids if nid is not None)
    failure_count = len(note_ids) - success_count
    return {"note_ids": note_ids, "success_count": success_count, "failure_count": failure_count}


@mcp.tool()
async def find_notes(query: str) -> dict:
    """
    Search for notes in Anki using its search syntax.
    
    Args:
        query: An Anki search query (e.g., 'deck:Default', 'tag:marked', 'front:apple').
        
    Returns:
        A dictionary with "query", "note_ids" (list of matching IDs), and "count".
    """
    note_ids = await invoke_anki("findNotes", query=query)
    return {"query": query, "note_ids": note_ids, "count": len(note_ids)}


@mcp.tool()
async def get_notes_info(note_ids: list[int]) -> dict:
    """
    Get detailed information about specific notes by their IDs.
    
    The output fields are simplified to a direct key-value mapping for easier reading.
    
    Args:
        note_ids: A list of note IDs to retrieve info for.
        
    Returns:
        A dictionary with "notes" (list of note info) and "count".
    """
    notes = await invoke_anki("notesInfo", notes=note_ids)
    
    simplified_notes = []
    for note in notes:
        # Simplify the fields structure from {"FieldName": {"value": "...", "order": 0}}
        # to just {"FieldName": "..."}
        simplified_fields = {
            name: data.get("value", "") 
            for name, data in note.get("fields", {}).items()
        }
        
        simplified_notes.append({
            "note_id": note.get("noteId"),
            "model_name": note.get("modelName"),
            "tags": note.get("tags", []),
            "fields": simplified_fields
        })
        
    return {"notes": simplified_notes, "count": len(simplified_notes)}


def main():
    """Run the MCP server with stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
