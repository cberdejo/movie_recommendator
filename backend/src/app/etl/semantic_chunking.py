from langchain_core.documents import Document

from app.entities.media_item_model import MediaItem


def build_semantic_documents_from_media_item(item: MediaItem) -> Document:
    """
    Builds a single semantic document from a MediaItem.
    """
    parts = [f"Title: {item.title or 'Unknown'}"]

    if item.type:
        parts.append(f"Type: {item.type}")
    if item.director:
        parts.append(f"Director: {item.director}")
    if item.genre:
        parts.append(f"Genres: {', '.join(item.genre)}")
    if item.cast:
        parts.append(f"Cast: {', '.join(item.cast)}")
    if item.duration_min:
        parts.append(f"Duration: {item.duration_min} minutes")
    if item.description:
        parts.append(f"Description: {item.description}")

    metadata = {
        "title": item.title,
        "type": item.type,
        "director": item.director,
        "genre": item.genre,
        "cast": item.cast,
        "duration_min": item.duration_min,
    }
    return Document(
        page_content="\n".join(parts),
        metadata={k: v for k, v in metadata.items() if v not in (None, "", [])},
    )
