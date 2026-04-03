"""
Prepare movie/media documents from CSV datasets.

- Loads two datasets (movies-only and mixed) with Polars.
- Merges rows into `MediaItem` objects.
- Builds a text corpus and metadata per item.

This module does NOT perform batch orchestration.
"""

from pathlib import Path
import ast
import re

import polars as pl

from app.core.config.logger import get_logger
from app.entities.media_item_model import MediaItem

log = get_logger("qdrant_populator")

DURATION_RE = re.compile(r"(\d+)\s*min", re.IGNORECASE)


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


def normalize_media_type(v) -> str | None:
    """Map source dataset labels to canonical internal media types."""
    if is_null(v):
        return None

    value = str(v).strip().lower()
    aliases = {
        "Movie": "movie",
        "TV Show": "series",
    }
    normalized = aliases.get(value)
    if normalized is None:
        log.warning("Unknown media type %r; leaving canonical media_type unset", v)
    return normalized


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
    # dataset 1
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
                    media_type="movie",
                )
            )
    # dataset 2
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
                    media_type=normalize_media_type(r.get("type")) or None,
                )
            )

    return unified
