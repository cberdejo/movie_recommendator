"""
Populate Qdrant collection in batches from CSV datasets.

CLI:
    python -m app.db.populate_movies_qdrant_batch \
        --movies /path/to/movies_csv_or_dir \
        --mixed /path/to/mixed_csv_or_dir \
        --batch-size 128
"""

import math
from pathlib import Path
from typing import Sequence
from tqdm import tqdm
import argparse
import asyncio
import ssl
import time

import kagglehub
import requests
import urllib3
from langchain_core.documents import Document

from app.core.config.logger import get_logger
from app.core.config.settings import qdrantsettings
from app.etl.media_dataset import load_unified
from app.services.retriever import HybridSearcher
from app.etl.semantic_chunking import build_semantic_documents_from_media_item

log = get_logger("qdrant_populator_batch")
MAX_RETRIES = 3  # Maximum number of retries for indexing a batch


def batched(seq: Sequence, size: int):
    """Generator that splits a sequence into fixed-size chunks."""
    if size <= 0:
        raise ValueError("size must be > 0")
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


async def index_all_with_batches(
    data: Sequence[Document],
    batch_size: int,
    verbose: bool = False,
) -> int:
    """
    Indexes all semantic documents in Qdrant using batches.
    Creates the collection once and reuses the same searcher.
    """
    if not data:
        return 0

    searcher = HybridSearcher(
        url=qdrantsettings.qdrant_endpoint,
        collection_name=qdrantsettings.qdrant_collection,
    )
    if verbose:
        log.info(
            "Resetting collection '%s' before indexing.",
            qdrantsettings.qdrant_collection,
        )
    await searcher.create_collection(recreate=True)

    total = 0

    for batch_number, batch in enumerate(
        tqdm(
            batched(list(data), batch_size),
            total=math.ceil(len(data) / batch_size),
            desc="Indexing batches",
        ),
        start=1,
    ):
        indexed = False
        for attempt in range(0, MAX_RETRIES):
            try:
                await searcher.index(list(batch), verbose=verbose)
                indexed = True
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    log.warning(
                        "Batch %d failed on attempt %d/3: %s. Retrying...",
                        batch_number,
                        attempt,
                        e,
                    )
                else:
                    log.error(
                        "Batch %d failed after %d attempts: %s",
                        batch_number,
                        MAX_RETRIES,
                        e,
                    )

        if not indexed:
            continue

        total += len(batch)

        if verbose:
            log.info(
                "Batch %d indexed: %d documents (total=%d)",
                batch_number,
                len(batch),
                total,
            )

    return total


def create_emb_db_from_csvs_in_batches(
    csv_movies_only: str | Path,
    csv_mixed_movies_tv: str | Path,
    batch_size: int,
    verbose: bool = False,
) -> int:
    """
    Loads datasets and indexes them in Qdrant using batched writes.
    """
    data = load_unified(csv_movies_only, csv_mixed_movies_tv)
    if not data:
        if verbose:
            log.info("No records to index.")
        return 0

    documents: list[Document] = list(
        map(build_semantic_documents_from_media_item, data)
    )

    if verbose:
        log.info("Built %d semantic documents.", len(documents))
        log.info("Documents (first 3): %s", documents[:3])
    total = asyncio.run(
        index_all_with_batches(
            data=documents,
            batch_size=batch_size,
            verbose=verbose,
        )
    )

    if verbose:
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
    parser = argparse.ArgumentParser(
        description="Populate Qdrant DB in batches using CSV files."
    )
    parser.add_argument(
        "-m", "--movies", type=str, help="Path to movies-only CSV file or directory"
    )
    parser.add_argument(
        "-x", "--mixed", type=str, help="Path to mixed movies/TV CSV file or directory"
    )
    parser.add_argument(
        "-b",
        "--batch-size",
        type=int,
        default=qdrantsettings.chunk_size,
        help="Batch size for indexing",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Mostrar información detallada de los lotes procesados",
    )
    args = parser.parse_args()

    if args.movies and args.mixed:
        movies_path, mixed_path = args.movies, args.mixed
    else:
        movies_path, mixed_path = _download_default_kaggle()

    total = create_emb_db_from_csvs_in_batches(
        movies_path,
        mixed_path,
        batch_size=args.batch_size,
        verbose=args.verbose,
    )
    if args.verbose:
        log.info("Done. Total indexed: %d", total)


if __name__ == "__main__":
    main()
