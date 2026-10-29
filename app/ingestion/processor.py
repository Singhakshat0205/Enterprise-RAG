# import os
# import sys
# import json
# import uuid
# import logging

# import logfire
# from qdrant_client import QdrantClient
# from qdrant_client.http import models

# from app.config import settings
# from app.services.retrieval.embeddings import (
#     EmbeddingRateLimitError,
#     embed_texts,
#     get_backend,
#     get_embedding_dim,
# )
# from app.ingestion.loaders.pdf import parse_pdf
# from app.ingestion.loaders.html import parse_html
# from app.ingestion.loaders.text import parse_text
# from app.ingestion.loaders.office import parse_office
# from app.ingestion.chunking.splitter import chunk_text


# PROCESSED_DATA_DIR = "processed_data"
# UPSERT_BATCH = 64

# logfire.configure(
#     service_name="enterprise-ingestion-service",
#     console=logfire.ConsoleOptions(min_log_level="info"),
# )
# logging.basicConfig(handlers=[logfire.LogfireLoggingHandler()])

# qdrant_client = QdrantClient(
#     url=settings.QDRANT_URL,
#     api_key=settings.QDRANT_API_KEY,
#     timeout=30,
# )


# def save_processed_locally(data: dict, source_type: str, filename: str) -> str:
#     folder = os.path.join(PROCESSED_DATA_DIR, source_type)
#     os.makedirs(folder, exist_ok=True)

#     dest = os.path.join(folder, f"{filename}.json")
#     with open(dest, "w", encoding="utf-8") as file:
#         json.dump(data, file, ensure_ascii=False, indent=2)

#     return dest


# def ensure_collection(client: QdrantClient, dim: int, wipe: bool):
#     """Create a correctly sized collection or validate the existing one."""
#     name = settings.QDRANT_COLLECTION

#     if wipe and client.collection_exists(name):
#         client.delete_collection(name)
#         logfire.warning(f"Wiped Qdrant collection '{name}'.")

#     if not client.collection_exists(name):
#         client.create_collection(
#             collection_name=name,
#             vectors_config=models.VectorParams(
#                 size=dim,
#                 distance=models.Distance.COSINE,
#             ),
#         )
#         logfire.info(f"Created Qdrant collection '{name}' ({dim}-dim).")
#         return

#     collection_info = client.get_collection(name)
#     existing_dim = collection_info.config.params.vectors.size

#     if existing_dim != dim:
#         raise RuntimeError(
#             f"Qdrant collection '{name}' expects {existing_dim}-dim vectors, "
#             f"but the selected embedding model produces {dim}-dim vectors. "
#             "Use --wipe to recreate the collection and re-ingest all documents, "
#             "or choose a new collection name."
#         )


# def process_file(
#     client: QdrantClient,
#     file_path: str,
#     filename: str,
#     source_type: str,
# ):
#     """Parse, chunk, save, embed, and index one file."""
#     with logfire.span("Processing File", file=filename, source=source_type):
#         try:
#             extension = filename.lower().rsplit(".", 1)[-1]

#             if extension == "pdf":
#                 full_text = parse_pdf(file_path)
#             elif extension in ("html", "htm"):
#                 full_text = parse_html(file_path)
#             elif extension == "txt":
#                 full_text = parse_text(file_path)
#             elif extension in ("docx", "pptx"):
#                 full_text = parse_office(file_path)
#             else:
#                 logfire.warning(f"Skipping unsupported file type: {filename}")
#                 return

#             if not full_text or not full_text.strip():
#                 logfire.warning(f"Skipping empty text content: {filename}")
#                 return

#             chunks = chunk_text(full_text)
#             if not chunks:
#                 logfire.warning(f"No chunks produced for {filename}.")
#                 return

#             local_path = save_processed_locally(
#                 {
#                     "filename": filename,
#                     "source_type": source_type,
#                     "chunks": chunks,
#                 },
#                 source_type,
#                 filename,
#             )
#             logfire.info(f"Saved processed data to {local_path}.")

#             # Remove previous points for this source before re-indexing the file.
#             client.delete(
#                 collection_name=settings.QDRANT_COLLECTION,
#                 points_selector=models.FilterSelector(
#                     filter=models.Filter(
#                         must=[
#                             models.FieldCondition(
#                                 key="source",
#                                 match=models.MatchValue(value=filename),
#                             )
#                         ]
#                     )
#                 ),
#             )

#             total_indexed = 0
#             for start in range(0, len(chunks), UPSERT_BATCH):
#                 batch = chunks[start : start + UPSERT_BATCH]
#                 logfire.info(
#                     f"Embedding chunks {start + 1}-{start + len(batch)} "
#                     f"of {len(chunks)} for {filename}."
#                 )

#                 vectors = embed_texts(batch)
#                 if len(vectors) != len(batch):
#                     raise RuntimeError(
#                         f"Embedding count mismatch for {filename}: "
#                         f"{len(batch)} chunks, {len(vectors)} vectors."
#                     )

#                 points = [
#                     models.PointStruct(
#                         id=str(
#                             uuid.uuid5(
#                                 uuid.NAMESPACE_URL,
#                                 f"{source_type}/{filename}/{start + index}",
#                             )
#                         ),
#                         vector=vector,
#                         payload={
#                             "text": chunk,
#                             "source": filename,
#                             "source_type": source_type,
#                             "chunk_index": start + index,
#                         },
#                     )
#                     for index, (chunk, vector) in enumerate(zip(batch, vectors))
#                 ]

#                 client.upsert(
#                     collection_name=settings.QDRANT_COLLECTION,
#                     points=points,
#                 )
#                 total_indexed += len(points)

#             logfire.info(
#                 f"Indexed {total_indexed} points from {filename} to Qdrant."
#             )

#         except EmbeddingRateLimitError:
#             # Do not swallow this: the directory and top-level run must stop.
#             logfire.exception(
#                 f"Stopping ingestion because Gemini rate limits persisted on {filename}."
#             )
#             raise
#         except Exception as e:
#             # Other file-specific errors are logged and processing continues.
#             logfire.exception(f"Failed to process {filename}: {e}")


# def process_directory(
#     client: QdrantClient,
#     directory: str,
#     source_type: str,
# ):
#     with logfire.span(
#         "Scanning Directory",
#         path=directory,
#         source=source_type,
#     ):
#         files = [
#             filename
#             for filename in os.listdir(directory)
#             if os.path.isfile(os.path.join(directory, filename))
#         ]
#         logfire.info(f"Found {len(files)} files in '{directory}'.")

#         for filename in files:
#             process_file(
#                 client,
#                 os.path.join(directory, filename),
#                 filename,
#                 source_type,
#             )


# def run_universal_ingestion(
#     client: QdrantClient,
#     base_dir: str,
#     explicit_source_type: str | None = None,
#     wipe: bool = False,
# ):
#     with logfire.span("Universal Ingestion Started", base_directory=base_dir):
#         # Select the backend and dimension before creating or validating Qdrant.
#         backend = get_backend()
#         dim = get_embedding_dim()
#         logfire.info(f"Using embedding backend '{backend}' ({dim}-dim).")

#         ensure_collection(client, dim, wipe)

#         subdirs = [
#             name
#             for name in os.listdir(base_dir)
#             if os.path.isdir(os.path.join(base_dir, name))
#         ]

#         if not subdirs:
#             if explicit_source_type:
#                 source_type = explicit_source_type
#             else:
#                 base_name = os.path.basename(os.path.normpath(base_dir)).lower()
#                 source_type = (
#                     "true"
#                     if "true" in base_name
#                     else "noisy"
#                     if "noisy" in base_name
#                     else "general"
#                 )

#             process_directory(client, base_dir, source_type)
#             return

#         for subdir in subdirs:
#             source_type = (
#                 "true"
#                 if "true" in subdir.lower()
#                 else "noisy"
#                 if "noisy" in subdir.lower()
#                 else subdir
#             )
#             process_directory(
#                 client,
#                 os.path.join(base_dir, subdir),
#                 source_type,
#             )


# def main():
#     args = [arg for arg in sys.argv[1:] if arg != "--wipe"]
#     wipe_requested = "--wipe" in sys.argv

#     target_dir = args[0] if args else "DATA"
#     explicit_type = args[1] if len(args) > 1 else None

#     if not os.path.exists(target_dir):
#         print(f"Error: path '{target_dir}' does not exist.")
#         return 1

#     print(
#         f"Starting ingestion on: {target_dir} "
#         f"(Type: {explicit_type}, wipe={wipe_requested})"
#     )

#     try:
#         run_universal_ingestion(
#             qdrant_client,
#             target_dir,
#             explicit_source_type=explicit_type,
#             wipe=wipe_requested,
#         )
#     except EmbeddingRateLimitError as e:
#         logfire.error(str(e))
#         print(f"Ingestion stopped: {e}", file=sys.stderr)
#         return 2
#     finally:
#         logfire.force_flush()

#     print("Ingestion completed.")
#     logfire.info("Ingestion job completed.")
#     return 0


# if __name__ == "__main__":
#     raise SystemExit(main())

import os

os.environ.setdefault("UNSTRUCTURED_DISABLE_NOTICE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import faulthandler
faulthandler.dump_traceback_later(300)   # one stack dump if the run is stuck for 5 minutes

import sys
import json
import uuid
import logging

import logfire
from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.config import settings
from app.services.retrieval.embeddings import (
    embed_texts, get_embedding_dim, get_backend, switch_to_fallback,
    backend_setting, pin_backend_for_dim, EmbeddingQuotaError,
)
from app.ingestion.loaders.pdf import parse_pdf
from app.ingestion.loaders.html import parse_html
from app.ingestion.loaders.text import parse_text
from app.ingestion.loaders.office import parse_office
from app.ingestion.chunking.splitter import chunk_text

PROCESSED_DATA_DIR = "processed_data"
UPSERT_BATCH = 64
INDEXED_FIELDS = ("source", "source_type")
STATE = {"dim": None}     # vector size of the collection currently being filled


def log(msg: str):
    print(msg, flush=True)


def setup():
    logfire.configure(
        service_name="enterprise-ingestion-service",
        send_to_logfire="if-token-present",
        console=logfire.ConsoleOptions(min_log_level="info"),
    )
    logging.basicConfig(handlers=[logfire.LogfireLoggingHandler()])
    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=30)


def pin_backend_to_existing_collection(client: QdrantClient):
    """In auto mode, keep using the model whose vectors match the existing collection."""
    name = settings.QDRANT_COLLECTION
    if backend_setting() == "auto" and client.collection_exists(name):
        existing = client.get_collection(name).config.params.vectors.size
        pin_backend_for_dim(existing)
        log(f"[*] Existing collection is {existing}-dim; using the matching embedding backend.")


def ensure_collection(client: QdrantClient, dim: int, wipe: bool):
    name = settings.QDRANT_COLLECTION

    if wipe and client.collection_exists(name):
        client.delete_collection(name)
        log(f"[*] Wiped collection '{name}'.")

    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        )
        log(f"[*] Created collection '{name}' ({dim}-dim, Cosine).")
    else:
        existing = client.get_collection(name).config.params.vectors.size
        if existing != dim:
            raise RuntimeError(
                f"Collection has {existing}-dim vectors but the embedding model gives {dim}. "
                f"Run with --wipe or keep EMBEDDING_BACKEND consistent."
            )

    STATE["dim"] = dim
    for field in INDEXED_FIELDS:
        client.create_payload_index(
            collection_name=name, field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )


def save_processed_locally(data: dict, source_type: str, filename: str) -> str:
    folder = os.path.join(PROCESSED_DATA_DIR, source_type)
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, f"{filename}.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return dest


def process_file(client: QdrantClient, file_path: str, filename: str, source_type: str):
    with logfire.span("Processing File", file=filename, source=source_type):
        try:
            ext = filename.lower().rsplit(".", 1)[-1]
            if ext == "pdf":
                full_text = parse_pdf(file_path)
            elif ext in ("html", "htm"):
                full_text = parse_html(file_path)
            elif ext == "txt":
                full_text = parse_text(file_path)
            elif ext in ("docx", "pptx"):
                full_text = parse_office(file_path)
            else:
                log(f"[-] Skipping unsupported file type: {filename}")
                return

            if not full_text or not full_text.strip():
                log(f"[-] Skipping empty text content: {filename}")
                return

            chunks = chunk_text(full_text)
            if not chunks:
                log(f"[-] No chunks produced: {filename}")
                return

            local_path = save_processed_locally(
                {"filename": filename, "source_type": source_type, "chunks": chunks},
                source_type, filename,
            )
            log(f"[+] Saved processed data -> {local_path} ({len(chunks)} chunks)")

            # Remove old points for THIS file in THIS source_type so re-runs don't duplicate
            client.delete(
                collection_name=settings.QDRANT_COLLECTION,
                points_selector=models.FilterSelector(
                    filter=models.Filter(must=[
                        models.FieldCondition(key="source", match=models.MatchValue(value=filename)),
                        models.FieldCondition(key="source_type", match=models.MatchValue(value=source_type)),
                    ])
                ),
            )

            with logfire.span("Vectorizing & Indexing"):
                total = 0
                for start in range(0, len(chunks), UPSERT_BATCH):
                    batch = chunks[start:start + UPSERT_BATCH]
                    log(f"    embedding chunks {start + 1}-{start + len(batch)} of {len(chunks)} ...")
                    vectors = embed_texts(batch)

                    # Never store a vector whose size differs from the collection's
                    wrong = {len(v) for v in vectors if len(v) != STATE["dim"]}
                    if wrong:
                        raise RuntimeError(
                            f"Vector size {wrong} does not match collection size {STATE['dim']}; refusing to upsert."
                        )

                    points = [
                        models.PointStruct(
                            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_type}/{filename}/{start + i}")),
                            vector=vector,
                            payload={
                                "text": chunk,
                                "source": filename,
                                "source_type": source_type,
                                "chunk_index": start + i,
                            },
                        )
                        for i, (chunk, vector) in enumerate(zip(batch, vectors))
                    ]
                    client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)
                    total += len(points)
                log(f"[+] Indexed {total} points to Qdrant from {filename}.")

        except EmbeddingQuotaError:
            raise          # let main() switch backend and restart the whole run
        except Exception as e:
            log(f"[!] Failed to process {filename}: {e}")
            logfire.exception("Failed to process {filename}", filename=filename)


def process_directory(client: QdrantClient, dir_path: str, source_type: str):
    with logfire.span("Scanning Directory", path=dir_path, source=source_type):
        files = [f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))]
        log(f"[*] Found {len(files)} files in '{dir_path}'.")
        for filename in files:
            process_file(client, os.path.join(dir_path, filename), filename, source_type)


def run_universal_ingestion(client: QdrantClient, base_dir: str,
                            explicit_source_type: str = None, wipe: bool = False):
    with logfire.span("Universal Ingestion Started", base_directory=base_dir):
        if not wipe:
            pin_backend_to_existing_collection(client)

        log("[*] Loading embedding model (first run may download ~400 MB)...")
        dim = get_embedding_dim()
        log(f"[*] Embedding backend: {get_backend()}, dimension: {dim}")

        ensure_collection(client, dim, wipe)

        subdirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]

        if not subdirs:
            if explicit_source_type:
                source_type = explicit_source_type
            else:
                base_name = os.path.basename(os.path.normpath(base_dir)).lower()
                source_type = ("true" if "true" in base_name
                               else "noisy" if "noisy" in base_name else "general")
            process_directory(client, base_dir, source_type)
        else:
            for subdir in subdirs:
                source_type = ("true" if "true" in subdir.lower()
                               else "noisy" if "noisy" in subdir.lower() else subdir)
                process_directory(client, os.path.join(base_dir, subdir), source_type)


def main():
    wipe_requested = "--wipe" in sys.argv
    args = [a for a in sys.argv if a != "--wipe"]
    target_dir = args[1] if len(args) > 1 else "DATA"
    explicit_type = args[2] if len(args) > 2 else None

    if not os.path.exists(target_dir):
        log(f"Error: path '{target_dir}' does not exist.")
        sys.exit(1)

    log(f"Starting ingestion on: {target_dir} (Type: {explicit_type}, wipe={wipe_requested})")
    client = setup()

    try:
        run_universal_ingestion(client, target_dir, explicit_type, wipe_requested)
    except EmbeddingQuotaError as e:
        log(f"[!] Gemini quota exhausted: {e}")
        log("[*] Switching to the local model and restarting from scratch.")
        log("    The collection will be wiped and rebuilt so every vector has the same size.")
        switch_to_fallback()
        run_universal_ingestion(client, target_dir, explicit_type, wipe=True)

    log("Ingestion function finished executing!")
    logfire.info("Ingestion job completed.")
    logfire.force_flush()


if __name__ == "__main__":
    main()