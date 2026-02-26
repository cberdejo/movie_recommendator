"""
Populate a Qdrant collection for HybridSearcher from CSV datasets (movies / movies+TV).

- Loads two datasets (movies-only and mixed) with Polars.
- Merges rows into `MediaItem` objects.
- Builds a text corpus and metadata per item.
- Indexes everything in Qdrant using `HybridSearcher` via `index_documents`.

CLI:
    python -m app.db.populate_movies_qdrant \\
        --movies /path/to/movies_csv_or_dir \\
        --mixed  /path/to/mixed_csv_or_dir

If no paths are provided, downloads the default Kaggle datasets.
"""

from pathlib import Path
from typing import Literal, Sequence
import argparse
import asyncio
import ast
import re
import ssl
import time

import kagglehub
import polars as pl
import requests
import urllib3
from langchain_core.documents import Document
from pydantic import BaseModel, Field

from app.core.config.logger import get_logger
from app.core.config.settings import qdrantsettings
from app.services.retriever import HybridSearcher
from app.entities.media_item_model import MediaItem


async def index_documents(corpora: Sequence[str], metadatas: Sequence[dict]) -> int:
    """
    Index a list of texts and metadata in Qdrant using the HybridSearcher.

    Args:
        corpora: List of texts already prepared (corpus) to index.
        metadatas: List of dictionaries of metadata associated with each text.

    Returns:
        Number of documents indexed.
    """
    if len(corpora) != len(metadatas):
        raise ValueError(
            f"corpora and metadatas must have the same length "
            f"(corpora={len(corpora)}, metadatas={len(metadatas)})"
        )

    searcher = HybridSearcher(
        url=qdrantsettings.qdrant_endpoint,
        collection_name=qdrantsettings.qdrant_collection,
    )
    await searcher.create_collection()

    documents = [
        Document(page_content=content, metadata=metadata)
        for content, metadata in zip(corpora, metadatas)
    ]
    await searcher.index(documents)
    return len(documents)


log = get_logger("qdrant_populator")

BATCH_SIZE = qdrantsettings.chunk_size
DURATION_RE = re.compile(r"(\\d+)\\s*min", re.IGNORECASE)


def as_path_glob(p: str | Path) -> str:
    """
    Returns a glob pattern to discover CSV files.

    - If `p` is a .csv file, returns the absolute path.
    - If `p` is a directory, returns recursive '**/*.csv' inside it.
    """
    p = Path(p).expanduser().resolve()
    if p.is_file() and p.suffix.lower() == ".csv":
        return str(p)
    return str(p / "**" / "*.csv")


def is_null(v) -> bool:
    """Safe null/NaN check."""
    try:
        import numpy as np  # type: ignore
    except Exception:
        np = None  # type: ignore

    if v is None:
        return True
    if np is not None and isinstance(v, float):
        return bool(np.isnan(v))
    return False


def split_csv_list(v) -> list[str]:
    """Splits a CSV string into a list of trimmed tokens."""
    return [] if is_null(v) else [x.strip() for x in str(v).split(",") if x.strip()]


def parse_listish(v) -> list[str]:
    """
    Parses list-like fields that may come as a Python list string or as CSV.
    """
    if is_null(v):
        return []
    s = str(v).strip()
    try:
        parsed = ast.literal_eval(s)
        if isinstance(parsed, list):
            return [
                str(x).strip().rstrip(",") for x in parsed if str(x).strip().rstrip(",")
            ]
    except Exception:
        pass
    return [x.strip().rstrip(",") for x in s.split(",") if x.strip().rstrip(",")]


def parse_duration_minutes(v) -> int | None:
    """Extracts minutes from strings like '30 min', returning None if no pattern matches."""
    if is_null(v):
        return None
    m = DURATION_RE.search(str(v))
    return int(m.group(1)) if m else None


def build_corpus(item: MediaItem) -> str:
    """Builds the corpus text from a `MediaItem`."""
    parts = [
        item.title or "",
        item.director or "",
        ", ".join(item.cast or []),
        ", ".join(item.genre or []),
        item.description or "",
        item.type or "",
        f"{item.duration_min} min" if item.duration_min else "",
    ]
    return " | ".join(p for p in parts if p)


def chunked(seq, size: int):
    """Generator that splits a sequence into fixed-size chunks."""
    if size <= 0:
        raise ValueError("size must be > 0")
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def load_unified(csv_movies_only: str | Path, csv_mixed: str | Path) -> list[MediaItem]:
    """
    Loads and unifies two datasets into a list of `MediaItem`.

    Dataset 1 (movies only): expected columns
        ['title', 'stars', 'genre', 'description', 'duration'].
    Dataset 2 (mixed movies/TV): expected columns
        ['title', 'director', 'cast', 'listed_in', 'description', 'duration', 'type'].

    Both parameters accept a CSV file or a directory (recursive glob is used).
    """
    pat1, pat2 = as_path_glob(csv_movies_only), as_path_glob(csv_mixed)

    try:
        df1 = pl.read_csv(
            pat1, glob=True, ignore_errors=True, quote_char='"', has_header=True
        )
    except Exception as e:
        log.warning("Failed to read dataset 1 (movies only): %s", e)
        df1 = pl.DataFrame()

    try:
        df2 = pl.read_csv(
            pat2, glob=True, ignore_errors=True, quote_char='"', has_header=True
        )
    except Exception as e:
        log.warning("Failed to read dataset 2 (mixed): %s", e)
        df2 = pl.DataFrame()

    unified: list[MediaItem] = []

    # ---- Dataset 1 (Movies) ----
    if df1.height > 0:
        cols1 = [
            c
            for c in ["title", "stars", "genre", "description", "duration"]
            if c in df1.columns
        ]
        for r in df1.select(cols1).to_dicts():
            unified.append(
                MediaItem(
                    title=r.get("title") or None,
                    director=None,
                    cast=parse_listish(r.get("stars")),
                    genre=split_csv_list(r.get("genre")),
                    description=r.get("description") or None,
                    duration_min=parse_duration_minutes(r.get("duration")),
                    type="Movie",
                )
            )

    # ---- Dataset 2 (Movies or TV) ----
    if df2.height > 0:
        cols2 = [
            c
            for c in [
                "title",
                "director",
                "cast",
                "listed_in",
                "description",
                "duration",
                "type",
            ]
            if c in df2.columns
        ]
        for r in df2.select(cols2).to_dicts():
            unified.append(
                MediaItem(
                    title=r.get("title") or None,
                    director=r.get("director") or None,
                    cast=parse_listish(r.get("cast")),
                    genre=split_csv_list(r.get("listed_in")),
                    description=r.get("description") or None,
                    duration_min=parse_duration_minutes(r.get("duration")),
                    type=r.get("type") or None,
                )
            )

    return unified


async def _index_all_with_hybrid(data: Sequence[MediaItem]) -> int:
    """
    Indexes all `MediaItem` in Qdrant using `HybridSearcher` (via `index_documents`).
    """
    total = 0
    for batch in chunked(list(data), BATCH_SIZE):
        corpora = [build_corpus(x) for x in batch]
        metadatas = [_build_metadata(x) for x in batch]
        indexed = await index_documents(corpora, metadatas)
        total += indexed
    return total


def _build_metadata(item: MediaItem) -> dict:
    """Builds the metadata dictionary for Qdrant."""
    payload = {
        "title": item.title,
        "director": item.director,
        "cast": item.cast,
        "genre": item.genre,
        "description": item.description,
        "duration_min": item.duration_min,
        "type": item.type,
    }
    return {k: v for k, v in payload.items() if v not in (None, "", [], {})}


def create_emb_db_from_csvs(csv_movies_only: str | Path, csv_mixed_movies_tv: str | Path) -> int:
    """
    Loads the datasets, builds the corpora and indexes them in Qdrant using HybridSearcher.
    """
    data = load_unified(csv_movies_only, csv_mixed_movies_tv)
    if not data:
        log.info("No records to index.")
        return 0

    total = asyncio.run(_index_all_with_hybrid(data))

    log.info(
        "Upsert completed in '%s' with %d elements.",
        qdrantsettings.qdrant_collection,
        total,
    )
    return total


def _download_default_kaggle() -> tuple[str, str]:
    """
    Downloads default Kaggle datasets if no paths are passed via CLI.

    Returns:
        (movies_only_path, mixed_path)
    """
    log.info("No CLI paths provided. Downloading Kaggle datasets...")

    import os

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    original_env = {}
    env_vars = {
        "PYTHONHTTPSVERIFY": "0",
        "REQUESTS_CA_BUNDLE": "",
        "CURL_CA_BUNDLE": "",
    }

    for key, value in env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    def _download_with_retry(dataset_name: str, max_retries: int = 3) -> str:
        for attempt in range(max_retries):
            try:
                log.info(
                    "Attempting to download dataset '%s' (attempt %d/%d)...",
                    dataset_name,
                    attempt + 1,
                    max_retries,
                )
                return kagglehub.dataset_download(dataset_name)
            except (
                requests.exceptions.SSLError,
                urllib3.exceptions.SSLError,
                ssl.SSLEOFError,
            ) as e:
                if attempt == max_retries - 1:
                    log.error(
                        "SSL error downloading dataset '%s' after %d attempts: %s",
                        dataset_name,
                        max_retries,
                        e,
                    )
                    raise
                log.warning(
                    "SSL error on attempt %d, retrying in %d seconds...",
                    attempt + 1,
                    2**attempt,
                )
                time.sleep(2**attempt)
            except Exception as e:
                if attempt == max_retries - 1:
                    log.error(
                        "Error downloading dataset '%s' after %d attempts: %s",
                        dataset_name,
                        max_retries,
                        e,
                    )
                    raise
                log.warning(
                    "Attempt %d failed, retrying in %d seconds... Error: %s",
                    attempt + 1,
                    2**attempt,
                    e,
                )
                time.sleep(2**attempt)

        raise RuntimeError(
            f"Could not download {dataset_name} after {max_retries} attempts"
        )

    try:
        imbd_path = _download_with_retry("payamamanat/imbd-dataset")
        netflix_path = _download_with_retry("shivamb/netflix-shows")
    finally:
        for key, original_value in original_env.items():
            if original_value is not None:
                os.environ[key] = original_value
            elif key in os.environ:
                del os.environ[key]

    return imbd_path, netflix_path


def main() -> None:
    """
    CLI entry point.

    Options:
        -m/--movies: Path to movies-only CSV (or directory).
        -x/--mixed : Path to mixed movies/TV CSV (or directory).

    If no paths are passed, default Kaggle datasets are downloaded.
    """
    parser = argparse.ArgumentParser(
        description="Populate Qdrant DB using CSV files (movies and mixed datasets)."
    )
    parser.add_argument(
        "-m", "--movies", type=str, help="Path to movies-only CSV file or directory"
    )
    parser.add_argument(
        "-x", "--mixed", type=str, help="Path to mixed movies/TV CSV file or directory"
    )
    args = parser.parse_args()

    if args.movies and args.mixed:
        movies_path, mixed_path = args.movies, args.mixed
    else:
        movies_path, mixed_path = _download_default_kaggle()

    total = create_emb_db_from_csvs(movies_path, mixed_path)
    log.info("Done. Total indexed: %d", total)


if __name__ == "__main__":
    main()

