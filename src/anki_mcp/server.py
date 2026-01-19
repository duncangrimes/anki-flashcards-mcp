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
import fitz  # PyMuPDF
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
    
    IMPORTANT: Always call this before add_notes to know the exact field names
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
# PDF Tools
# =============================================================================

@mcp.tool()
def get_pdf_table_of_contents(file_path: str) -> dict:
    """
    Get the Table of Contents (outline) from a PDF file.
    
    Use this tool FIRST when working with PDFs to understand the document structure
    and find which pages correspond to specific chapters or sections.
    
    Args:
        file_path: The absolute path to the PDF file.
        
    Returns:
        A dictionary with "toc" (list of entries) and "count".
        Each entry contains: level (int), title (str), page (int).
        
    Example:
        >>> get_pdf_table_of_contents("/path/to/textbook.pdf")
        {
            "toc": [
                {"level": 1, "title": "Chapter 1: Introduction", "page": 1},
                {"level": 2, "title": "1.1 Background", "page": 3},
                ...
            ],
            "count": 15
        }
    """
    try:
        doc = fitz.open(file_path)
        toc = doc.get_toc()
        doc.close()
        
        if not toc:
            return {
                "toc": [],
                "count": 0,
                "message": "No Table of Contents found in this PDF. Use read_pdf_pages to explore manually."
            }
        
        entries = []
        for level, title, page in toc:
            entries.append({"level": level, "title": title, "page": page})
        
        return {"toc": entries, "count": len(entries)}
    except Exception as e:
        return {"error": f"Error reading PDF: {str(e)}"}


@mcp.tool()
def read_pdf_pages(file_path: str, start_page: int, end_page: int) -> dict:
    """
    Extract text content from a range of pages in a PDF file.
    
    Use get_pdf_table_of_contents() first to identify which pages to read,
    then use this tool to extract the text content for flashcard creation.
    
    Args:
        file_path: The absolute path to the PDF file.
        start_page: The first page to read (1-indexed, inclusive).
        end_page: The last page to read (1-indexed, inclusive).
        
    Returns:
        A dictionary with "pages" (list of page content), "page_count", and "total_pages".
        
    Example:
        >>> read_pdf_pages("/path/to/textbook.pdf", 10, 12)
        {
            "pages": [
                {"page": 10, "text": "Chapter 5: Photosynthesis..."},
                {"page": 11, "text": "The process begins when..."},
                {"page": 12, "text": "In summary, photosynthesis..."}
            ],
            "page_count": 3,
            "total_pages": 200
        }
    """
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        
        # Validate range (PyMuPDF is 0-indexed, users provide 1-indexed)
        start_idx = max(0, start_page - 1)
        end_idx = min(total_pages, end_page)
        
        if start_idx >= total_pages:
            doc.close()
            return {"error": f"Start page {start_page} exceeds document length ({total_pages} pages)"}
        
        pages = []
        for i in range(start_idx, end_idx):
            page = doc.load_page(i)
            text = page.get_text()
            pages.append({"page": i + 1, "text": text})
        
        doc.close()
        return {
            "pages": pages,
            "page_count": len(pages),
            "total_pages": total_pages
        }
    except Exception as e:
        return {"error": f"Error reading PDF pages: {str(e)}"}


# =============================================================================
# Note (Card) Tools
# =============================================================================

@mcp.tool()
async def add_notes(notes: list[dict]) -> dict:
    """
    Add multiple notes (flashcards) to Anki in a single batch.
    
    Before calling this tool:
    1. Use get_deck_names() to verify the deck exists (or create_deck() to make it)
    2. Use get_model_names() to find available Note Types
    3. Use get_model_field_names() to get the exact field names for your chosen model
    
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


@mcp.tool()
async def delete_notes(note_ids: list[int]) -> dict:
    """
    Delete notes from Anki by their IDs.
    
    WARNING: This permanently deletes notes and ALL their associated cards.
    This action cannot be undone unless you have a backup.
    
    Typical workflow:
    1. Use find_notes() to search for notes matching your criteria
    2. Optionally use get_notes_info() to inspect the notes
    3. Call delete_notes() with the IDs to delete
    
    Args:
        note_ids: A list of note IDs to delete. Get these from find_notes().
        
    Returns:
        A dictionary with "deleted_count" indicating how many notes were deleted.
        
    Example:
        >>> # Find and delete all notes about mitosis in the Biology deck
        >>> result = find_notes("deck:Biology mitosis")
        >>> # result: {"note_ids": [123, 456, 789], "count": 3}
        >>> delete_notes([123, 456, 789])
        {"deleted_count": 3}
    """
    if not note_ids:
        return {"deleted_count": 0, "message": "No note IDs provided"}
    
    await invoke_anki("deleteNotes", notes=note_ids)
    return {"deleted_count": len(note_ids)}


@mcp.tool()
async def update_notes(note_ids: list[int], updates: dict) -> dict:
    """
    Update existing notes without deleting and recreating them.
    
    This preserves:
    - Note IDs and creation timestamps
    - Review history and scheduling data
    - Card statistics and learning progress
    
    Supported updates:
    - deck_name: Move notes to a different deck (preserves review history)
    - fields: Update field values (e.g., {"Front": "new front", "Back": "new back"})
    - tags_add: Add tags to notes (list of tag strings)
    - tags_remove: Remove tags from notes (list of tag strings)
    
    Args:
        note_ids: A list of note IDs to update.
        updates: A dictionary specifying what to update:
                 - "deck_name": str - Move cards to this deck
                 - "fields": dict - Update field values {field_name: new_value}
                 - "tags_add": list[str] - Tags to add
                 - "tags_remove": list[str] - Tags to remove
        
    Returns:
        A dictionary with "updated_count", "failed_count", and "operations" summary.
        
    Examples:
        >>> # Move notes to a different deck
        >>> update_notes([123, 456], {"deck_name": "System Design"})
        {"updated_count": 2, "failed_count": 0, "operations": ["deck_change"]}
        
        >>> # Update field values
        >>> update_notes([123], {"fields": {"Front": "Updated question", "Back": "Updated answer"}})
        {"updated_count": 1, "failed_count": 0, "operations": ["fields_update"]}
        
        >>> # Add and remove tags
        >>> update_notes([123, 456], {"tags_add": ["important", "review"], "tags_remove": ["old-tag"]})
        {"updated_count": 2, "failed_count": 0, "operations": ["tags_add", "tags_remove"]}
        
        >>> # Combine multiple operations
        >>> update_notes([123], {
        ...     "deck_name": "New Deck",
        ...     "fields": {"Front": "New front"},
        ...     "tags_add": ["new-tag"]
        ... })
        {"updated_count": 1, "failed_count": 0, "operations": ["deck_change", "fields_update", "tags_add"]}
    """
    if not note_ids:
        return {"updated_count": 0, "failed_count": 0, "message": "No note IDs provided", "operations": []}
    
    operations = []
    errors = []
    
    try:
        # 1. Handle deck change (requires card IDs)
        if "deck_name" in updates:
            deck_name = updates["deck_name"]
            try:
                # Get note info to extract card IDs
                notes_info = await invoke_anki("notesInfo", notes=note_ids)
                card_ids = []
                for note in notes_info:
                    card_ids.extend(note.get("cards", []))
                
                if card_ids:
                    await invoke_anki("changeDeck", cards=card_ids, deck=deck_name)
                    operations.append("deck_change")
                else:
                    errors.append("No cards found for the given notes")
            except Exception as e:
                errors.append(f"Deck change failed: {str(e)}")
        
        # 2. Handle field updates
        if "fields" in updates:
            fields = updates["fields"]
            try:
                for note_id in note_ids:
                    await invoke_anki("updateNoteFields", note={"id": note_id, "fields": fields})
                operations.append("fields_update")
            except Exception as e:
                errors.append(f"Fields update failed: {str(e)}")
        
        # 3. Handle adding tags
        if "tags_add" in updates:
            tags = updates["tags_add"]
            try:
                if isinstance(tags, list):
                    tags_str = " ".join(tags)
                else:
                    tags_str = tags
                await invoke_anki("addTags", notes=note_ids, tags=tags_str)
                operations.append("tags_add")
            except Exception as e:
                errors.append(f"Add tags failed: {str(e)}")
        
        # 4. Handle removing tags
        if "tags_remove" in updates:
            tags = updates["tags_remove"]
            try:
                if isinstance(tags, list):
                    tags_str = " ".join(tags)
                else:
                    tags_str = tags
                await invoke_anki("removeTags", notes=note_ids, tags=tags_str)
                operations.append("tags_remove")
            except Exception as e:
                errors.append(f"Remove tags failed: {str(e)}")
        
        # Determine success/failure
        if errors:
            return {
                "updated_count": len(note_ids) if operations else 0,
                "failed_count": len(note_ids) if not operations else 0,
                "operations": operations,
                "errors": errors,
                "partial_success": len(operations) > 0 and len(errors) > 0
            }
        else:
            return {
                "updated_count": len(note_ids),
                "failed_count": 0,
                "operations": operations
            }
            
    except Exception as e:
        return {
            "updated_count": 0,
            "failed_count": len(note_ids),
            "operations": operations,
            "error": f"Update failed: {str(e)}"
        }


def main():
    """Run the MCP server with stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
