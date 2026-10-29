# # # import os
# # # import sys
# # # import time
# # # import threading

# # # import logfire
# # # from dotenv import load_dotenv

# # # load_dotenv()   # so EMBEDDING_BACKEND / keys in .env are visible below

# # # from app.config import settings

# # # BATCH_SIZE = 50
# # # PROBE_TIMEOUT_S = 15
# # # GEMINI_MODEL = "models/gemini-embedding-2-preview"
# # # FALLBACK_MODEL = "all-mpnet-base-v2"   # 768-dim

# # # # EMBEDDING_BACKEND: "auto" (try Gemini, else local), "gemini" (fail if unavailable),
# # # # or "fallback" (local model only). Keep it fixed per collection: the two models
# # # # produce different vector sizes.
# # # _FORCED_BACKEND = os.getenv("EMBEDDING_BACKEND", "auto").strip().lower()

# # # _active_model = None
# # # _model_type: str | None = None   # "gemini" or "fallback"
# # # _dim: int | None = None


# # # def _say(level: str, msg: str):
# # #     """Log to Logfire and also print, so problems are visible without a dashboard."""
# # #     print(f"[embeddings] {msg}", file=sys.stderr, flush=True)
# # #     getattr(logfire, level)(msg)


# # # def _probe_gemini():
# # #     """Try one embed call with a hard timeout. Returns (model, dim) or (None, None)."""
# # #     result = {}

# # #     def _try():
# # #         try:
# # #             from langchain_google_genai import GoogleGenerativeAIEmbeddings
# # #             model = GoogleGenerativeAIEmbeddings(
# # #                 model=GEMINI_MODEL,
# # #                 google_api_key=settings.GEMINI_API_KEY,
# # #             )
# # #             vec = model.embed_query("probe")
# # #             result["model"], result["dim"] = model, len(vec)
# # #         except Exception as e:
# # #             result["error"] = f"{type(e).__name__}: {e}"

# # #     t = threading.Thread(target=_try, daemon=True)
# # #     t.start()
# # #     t.join(PROBE_TIMEOUT_S)

# # #     if t.is_alive():
# # #         _say("warning", f"Gemini probe timed out after {PROBE_TIMEOUT_S}s (network or API issue).")
# # #         return None, None
# # #     if "error" in result:
# # #         _say("warning", f"Gemini probe failed: {result['error']}")
# # #         return None, None
# # #     return result["model"], result["dim"]


# # # def _load_fallback():
# # #     from sentence_transformers import SentenceTransformer
# # #     _say("info", f"Loading local embedding model ({FALLBACK_MODEL}).")
# # #     model = SentenceTransformer(FALLBACK_MODEL)
# # #     get_dim = getattr(model, "get_embedding_dimension", None) \
# # #         or model.get_sentence_embedding_dimension
# # #     return model, get_dim()


# # # def _init():
# # #     global _active_model, _model_type, _dim

# # #     if _active_model is not None:
# # #         return

# # #     _say("info", f"Embedding backend setting: '{_FORCED_BACKEND}'")

# # #     if _FORCED_BACKEND == "fallback":
# # #         _active_model, _dim = _load_fallback()
# # #         _model_type = "fallback"
# # #     else:
# # #         model, dim = _probe_gemini()
# # #         if model is not None:
# # #             _active_model, _model_type, _dim = model, "gemini", dim
# # #         elif _FORCED_BACKEND == "gemini":
# # #             raise RuntimeError(
# # #                 "EMBEDDING_BACKEND=gemini but the Gemini probe failed (see the warning above)."
# # #             )
# # #         else:
# # #             _say("warning", "Falling back to the local model.")
# # #             _active_model, _dim = _load_fallback()
# # #             _model_type = "fallback"

# # #     _say("info", f"Active embedding backend: {_model_type} ({_dim}-dim).")


# # # def get_backend() -> str:
# # #     """'gemini' or 'fallback' (initializes the model if needed)."""
# # #     _init()
# # #     return _model_type


# # # def get_embedding_dim() -> int:
# # #     """Vector dimension of the active model."""
# # #     _init()
# # #     return _dim


# # # # def _embed_batch(batch: list[str]) -> list[list[float]]:
# # # #     global _active_model, _model_type, _dim

# # # #     if _model_type == "gemini":
# # # #         for attempt in range(4):
# # # #             try:
# # # #                 return _active_model.embed_documents(batch)
# # # #             except Exception as e:
# # # #                 err = str(e).lower()
# # # #                 is_rate_limit = any(
# # # #                     x in err for x in ("429", "rate", "quota", "resource_exhausted")
# # # #                 )
# # # #                 if not is_rate_limit:
# # # #                     raise  # Surface non-rate-limit errors immediately.

# # # #                 if attempt == 3:
# # # #                     _say(
# # # #                         "warning",
# # # #                         "Gemini rate limit persisted after 4 attempts. Switching to local model."
# # # #                     )
# # # #                     _active_model, _dim = _load_fallback()
# # # #                     _model_type = "fallback"
# # # #                     return _active_model.encode(
# # # #                         batch, show_progress_bar=False
# # # #                     ).tolist()

# # # #                 wait = 2 ** attempt
# # # #                 logfire.warning(
# # # #                     "Gemini rate limit hit - retrying in {wait}s (attempt {n}/4)",
# # # #                     wait=wait,
# # # #                     n=attempt + 1,
# # # #                 )
# # # #                 time.sleep(wait)

# # # #     return _active_model.encode(batch, show_progress_bar=False).tolist()

# # # def _embed_batch(batch: list[str]) -> list[list[float]]:
# # #     global _active_model, _model_type, _dim

# # #     if _model_type == "gemini":
# # #         for attempt in range(4):
# # #             try:
# # #                 return _active_model.embed_documents(batch)
# # #             except Exception as e:
# # #                 err = f"{type(e).__name__}: {e}".lower()
# # #                 is_rate_limit = any(
# # #                     marker in err
# # #                     for marker in (
# # #                         "429",
# # #                         "rate limit",
# # #                         "rate_limit",
# # #                         "quota",
# # #                         "resource_exhausted",
# # #                         "resource exhausted",
# # #                         "too many requests",
# # #                     )
# # #                 )

# # #                 if not is_rate_limit:
# # #                     raise

# # #                 if attempt < 3:
# # #                     wait = 2 ** attempt
# # #                     _say(
# # #                         "warning",
# # #                         f"Gemini rate limit on attempt {attempt + 1}/4; "
# # #                         f"retrying in {wait}s: {e}",
# # #                     )
# # #                     time.sleep(wait)
# # #                     continue

# # #                 _say(
# # #                     "warning",
# # #                     f"Gemini rate limit persisted after 4 attempts; "
# # #                     f"switching to local model. Last error: {e}",
# # #                 )
# # #                 _active_model, _dim = _load_fallback()
# # #                 _model_type = "fallback"
# # #                 return _active_model.encode(
# # #                     batch, show_progress_bar=False
# # #                 ).tolist()

# # #     return _active_model.encode(batch, show_progress_bar=False).tolist()


# # # def embed_query(query: str) -> list[float]:
# # #     _init()
# # #     if _model_type == "gemini":
# # #         return _active_model.embed_query(query)
# # #     return _active_model.encode([query])[0].tolist()


# # # def embed_texts(texts: list[str]) -> list[list[float]]:
# # #     _init()
# # #     all_embeddings: list[list[float]] = []
# # #     for i in range(0, len(texts), BATCH_SIZE):
# # #         batch = texts[i:i + BATCH_SIZE]
# # #         with logfire.span("Embed batch", model=_model_type, start=i, size=len(batch)):
# # #             all_embeddings.extend(_embed_batch(batch))
# # #     return all_embeddings




# # import os
# # import sys
# # import time
# # import threading

# # import logfire
# # from dotenv import load_dotenv

# # load_dotenv()   # so EMBEDDING_BACKEND / keys in .env are visible below

# # from app.config import settings

# # BATCH_SIZE = 50
# # PROBE_TIMEOUT_S = 15
# # GEMINI_MODEL = "models/gemini-embedding-2-preview"
# # FALLBACK_MODEL = "all-mpnet-base-v2"   # 768-dim

# # # EMBEDDING_BACKEND: "auto" (try Gemini, else local), "gemini" (fail if unavailable),
# # # or "fallback" (local model only). Keep it fixed per collection: the two models
# # # produce different vector sizes.
# # _FORCED_BACKEND = os.getenv("EMBEDDING_BACKEND", "fallback").strip().lower()

# # _active_model = None
# # _model_type: str | None = None   # "gemini" or "fallback"
# # _dim: int | None = None


# # def _say(level: str, msg: str):
# #     """Log to Logfire and also print, so problems are visible without a dashboard."""
# #     print(f"[embeddings] {msg}", file=sys.stderr, flush=True)
# #     getattr(logfire, level)(msg)


# # def _probe_gemini():
# #     """Try one embed call with a hard timeout. Returns (model, dim) or (None, None)."""
# #     result = {}

# #     def _try():
# #         try:
# #             from langchain_google_genai import GoogleGenerativeAIEmbeddings
# #             model = GoogleGenerativeAIEmbeddings(
# #                 model=GEMINI_MODEL,
# #                 google_api_key=settings.GEMINI_API_KEY,
# #             )
# #             vec = model.embed_query("probe")
# #             result["model"], result["dim"] = model, len(vec)
# #         except Exception as e:
# #             result["error"] = f"{type(e).__name__}: {e}"

# #     t = threading.Thread(target=_try, daemon=True)   # daemon: can't block interpreter exit
# #     t.start()
# #     t.join(PROBE_TIMEOUT_S)

# #     if t.is_alive():
# #         _say("warning", f"Gemini probe timed out after {PROBE_TIMEOUT_S}s (network or API issue).")
# #         return None, None
# #     if "error" in result:
# #         _say("warning", f"Gemini probe failed: {result['error']}")
# #         return None, None
# #     return result["model"], result["dim"]


# # def _load_fallback():
# #     from sentence_transformers import SentenceTransformer
# #     _say("info", f"Loading local embedding model ({FALLBACK_MODEL}).")
# #     model = SentenceTransformer(FALLBACK_MODEL)
# #     get_dim = getattr(model, "get_embedding_dimension", None) \
# #         or model.get_sentence_embedding_dimension      # older sentence-transformers
# #     return model, get_dim()


# # def _init():
# #     global _active_model, _model_type, _dim

# #     if _active_model is not None:
# #         return

# #     _say("info", f"Embedding backend setting: '{_FORCED_BACKEND}'")

# #     if _FORCED_BACKEND == "fallback":
# #         _active_model, _dim = _load_fallback()
# #         _model_type = "fallback"
# #     else:
# #         model, dim = _probe_gemini()
# #         if model is not None:
# #             _active_model, _model_type, _dim = model, "gemini", dim
# #         else:
# #             _say("warning", "Gemini probe failed. Falling back to the local model.")
# #             _active_model, _dim = _load_fallback()
# #             _model_type = "fallback"

# #     _say("info", f"Active embedding backend: {_model_type} ({_dim}-dim).")


# # def get_backend() -> str:
# #     """'gemini' or 'fallback' (initializes the model if needed)."""
# #     _init()
# #     return _model_type


# # def get_embedding_dim() -> int:
# #     """Vector dimension of the active model."""
# #     _init()
# #     return _dim


# # def _ensure_fallback():
# #     """Switch to the local model once after Gemini fails."""
# #     global _active_model, _model_type, _dim
# #     if _model_type != "fallback":
# #         _say("warning", "Switching to local fallback embeddings.")
# #         _active_model, _dim = _load_fallback()
# #         _model_type = "fallback"


# # def _embed_gemini_batch(batch: list[str]) -> list[list[float]]:
# #     """Try Gemini up to four times, then let the caller handle fallback."""
# #     last_error = None
# #     for attempt in range(4):
# #         try:
# #             return _active_model.embed_documents(batch)
# #         except Exception as e:
# #             last_error = e
# #             if attempt < 3:
# #                 wait = 2 ** attempt
# #                 _say(
# #                     "warning",
# #                     f"Gemini embedding failed (attempt {attempt + 1}/4): {e}. "
# #                     f"Retrying in {wait}s.",
# #                 )
# #                 time.sleep(wait)
# #     raise RuntimeError("Gemini embedding failed after 4 attempts.") from last_error


# # def _embed_batch(batch: list[str]) -> list[list[float]]:
# #     """Embed one batch via Gemini, switching to local model after repeated failure."""
# #     if _model_type == "gemini":
# #         try:
# #             return _embed_gemini_batch(batch)
# #         except Exception as e:
# #             _say("error", f"Gemini failed after retries: {e}. Falling back to local model.")
# #             _ensure_fallback()

# #     return _active_model.encode(batch, show_progress_bar=False).tolist()


# # def embed_query(query: str) -> list[float]:
# #     _init()
# #     if _model_type == "gemini":
# #         try:
# #             # Reuse the bounded retry and fallback behavior for a single query.
# #             return _embed_gemini_query(query)
# #         except Exception as e:
# #             _say("error", f"Gemini query embedding failed after retries: {e}. Falling back.")
# #             _ensure_fallback()
# #     return _active_model.encode([query], show_progress_bar=False)[0].tolist()


# # def _embed_gemini_query(query: str) -> list[float]:
# #     """Try one Gemini query embedding up to four times."""
# #     last_error = None
# #     for attempt in range(4):
# #         try:
# #             return _active_model.embed_query(query)
# #         except Exception as e:
# #             last_error = e
# #             if attempt < 3:
# #                 wait = 2 ** attempt
# #                 _say("warning", f"Gemini query failed (attempt {attempt + 1}/4): {e}. Retrying in {wait}s.")
# #                 time.sleep(wait)
# #     raise RuntimeError("Gemini query embedding failed after 4 attempts.") from last_error


# # def embed_texts(texts: list[str]) -> list[list[float]]:
# #     _init()
# #     all_embeddings: list[list[float]] = []
# #     for i in range(0, len(texts), BATCH_SIZE):
# #         batch = texts[i:i + BATCH_SIZE]
# #         with logfire.span("Embed batch", model=_model_type, start=i, size=len(batch)):
# #             all_embeddings.extend(_embed_batch(batch))
# #     return all_embeddings



# import os
# import time

# import logfire
# from dotenv import load_dotenv
# from langchain_google_genai import GoogleGenerativeAIEmbeddings

# load_dotenv()

# from app.config import settings

# BATCH_SIZE = 50
# GEMINI_MODEL = "models/gemini-embedding-2-preview"
# FALLBACK_MODEL = "all-mpnet-base-v2"

# # "auto" tries Gemini at startup, then uses local if the probe fails.
# # "fallback" uses the local model from the start.
# _EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "auto").strip().lower()

# _active_model = None
# _model_type: str | None = None
# _dim: int | None = None


# class EmbeddingRateLimitError(RuntimeError):
#     """Raised when Gemini rate limits persist after bounded retries."""


# def _is_rate_limit_error(error: Exception) -> bool:
#     message = f"{type(error).__name__}: {error}".lower()
#     return any(
#         marker in message
#         for marker in (
#             "429",
#             "rate limit",
#             "rate_limit",
#             "quota",
#             "resource_exhausted",
#             "resource exhausted",
#             "too many requests",
#         )
#     )


# def _probe_gemini():
#     """Return (Gemini model, vector dimension), or (None, None) if unavailable."""
#     if not settings.GEMINI_API_KEY:
#         logfire.warning("GEMINI_API_KEY is missing; using local embeddings.")
#         return None, None

#     try:
#         model = GoogleGenerativeAIEmbeddings(
#             model=GEMINI_MODEL,
#             google_api_key=settings.GEMINI_API_KEY,
#         )
#         vector = model.embed_query("embedding connectivity probe")
#         dim = len(vector)

#         logfire.info(f"Gemini embeddings ready ({GEMINI_MODEL}, {dim}-dim).")
#         return model, dim
#     except Exception as e:
#         logfire.warning(f"Gemini probe failed: {e}. Using local embeddings.")
#         return None, None


# def _load_fallback():
#     """Load the local model and return it with its actual vector dimension."""
#     from sentence_transformers import SentenceTransformer

#     logfire.info(f"Loading local embedding model ({FALLBACK_MODEL}).")
#     model = SentenceTransformer(FALLBACK_MODEL)

#     get_dim = getattr(model, "get_embedding_dimension", None)
#     if get_dim is None:
#         get_dim = model.get_sentence_embedding_dimension

#     return model, get_dim()


# def _init():
#     """Choose and load one model for this process."""
#     global _active_model, _model_type, _dim

#     if _active_model is not None:
#         return

#     logfire.info(f"Embedding backend setting: '{_EMBEDDING_BACKEND}'")

#     if _EMBEDDING_BACKEND == "fallback":
#         _active_model, _dim = _load_fallback()
#         _model_type = "fallback"
#     else:
#         gemini_model, gemini_dim = _probe_gemini()

#         if gemini_model is not None:
#             _active_model = gemini_model
#             _model_type = "gemini"
#             _dim = gemini_dim
#         else:
#             _active_model, _dim = _load_fallback()
#             _model_type = "fallback"

#     logfire.info(f"Active embedding backend: {_model_type} ({_dim}-dim).")


# def get_backend() -> str:
#     _init()
#     return _model_type


# def get_embedding_dim() -> int:
#     _init()
#     return _dim


# def _call_gemini_with_retries(call, operation: str):
#     """Retry rate limits a bounded number of times, then raise without switching."""
#     for attempt in range(4):
#         try:
#             return call()
#         except Exception as e:
#             if not _is_rate_limit_error(e):
#                 raise

#             if attempt == 3:
#                 raise EmbeddingRateLimitError(
#                     f"Gemini rate limit persisted after 4 attempts while {operation}. "
#                     "Stop this run; restart the complete ingestion with "
#                     "EMBEDDING_BACKEND=fallback and --wipe to use one model throughout."
#                 ) from e

#             wait_seconds = 2 ** attempt
#             logfire.warning(
#                 f"Gemini rate limit while {operation}; "
#                 f"retrying in {wait_seconds}s (attempt {attempt + 1}/4)."
#             )
#             time.sleep(wait_seconds)


# def _embed_batch(batch: list[str]) -> list[list[float]]:
#     _init()

#     if _model_type == "gemini":
#         vectors = _call_gemini_with_retries(
#             lambda: _active_model.embed_documents(batch),
#             "embedding a document batch",
#         )
#         if vectors and len(vectors[0]) != _dim:
#             raise RuntimeError(
#                 f"Gemini returned {len(vectors[0])}-dim vectors, "
#                 f"but the startup probe returned {_dim}-dim vectors."
#             )
#         return vectors

#     vectors = _active_model.encode(batch, show_progress_bar=False).tolist()
#     if vectors and len(vectors[0]) != _dim:
#         raise RuntimeError(
#             f"Local model returned {len(vectors[0])}-dim vectors; expected {_dim}."
#         )
#     return vectors


# def embed_query(query: str) -> list[float]:
#     _init()

#     if _model_type == "gemini":
#         vector = _call_gemini_with_retries(
#             lambda: _active_model.embed_query(query),
#             "embedding a query",
#         )
#         if len(vector) != _dim:
#             raise RuntimeError(
#                 f"Gemini returned a {len(vector)}-dim query vector; expected {_dim}."
#             )
#         return vector

#     vector = _active_model.encode([query], show_progress_bar=False)[0].tolist()
#     if len(vector) != _dim:
#         raise RuntimeError(
#             f"Local model returned a {len(vector)}-dim query vector; expected {_dim}."
#         )
#     return vector


# def embed_texts(texts: list[str]) -> list[list[float]]:
#     _init()

#     all_embeddings: list[list[float]] = []
#     for start in range(0, len(texts), BATCH_SIZE):
#         batch = texts[start : start + BATCH_SIZE]
#         with logfire.span(
#             "Embed batch",
#             model=_model_type,
#             start=start,
#             size=len(batch),
#         ):
#             all_embeddings.extend(_embed_batch(batch))

#     return all_embeddings


import os
import re
import sys
import time
import threading
import collections

import logfire
from dotenv import load_dotenv

load_dotenv()   # so EMBEDDING_BACKEND / keys in .env are visible below

from app.config import settings

BATCH_SIZE = 50                                                   # local model batch
GEMINI_BATCH = int(os.getenv("GEMINI_BATCH", "20"))
GEMINI_MAX_PER_MIN = int(os.getenv("GEMINI_MAX_PER_MIN", "80"))   # free tier limit is 100
GEMINI_QUOTA_RETRIES = int(os.getenv("GEMINI_QUOTA_RETRIES", "1"))  # waits before giving up
MAX_WAIT_S = 90
PROBE_TIMEOUT_S = 15
GEMINI_MODEL = "models/gemini-embedding-2-preview"
FALLBACK_MODEL = "all-mpnet-base-v2"
FALLBACK_DIM = 768

# "auto" (try Gemini, else local), "gemini" (fail if unavailable), "fallback" (local only)
_backend_setting = os.getenv("EMBEDDING_BACKEND", "auto").strip().lower()

_active_model = None
_model_type: str | None = None   # "gemini" or "fallback"
_dim: int | None = None
_sent = collections.deque()      # (timestamp, n_texts) sent to Gemini in the last minute


class EmbeddingQuotaError(RuntimeError):
    """Gemini quota is exhausted: the caller should switch backend and restart."""


def _say(level: str, msg: str):
    print(f"[embeddings] {msg}", file=sys.stderr, flush=True)
    getattr(logfire, level)(msg)


# ---------- backend selection ----------

def backend_setting() -> str:
    return _backend_setting


def set_backend(name: str):
    """Choose 'auto' | 'gemini' | 'fallback' and reset any loaded model."""
    global _backend_setting, _active_model, _model_type, _dim
    _backend_setting = name
    _active_model, _model_type, _dim = None, None, None


def pin_backend_for_dim(dim: int):
    """Pick the backend whose vectors match an existing collection's size."""
    set_backend("fallback" if dim == FALLBACK_DIM else "gemini")


def _probe_gemini():
    result = {}

    def _try():
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            model = GoogleGenerativeAIEmbeddings(
                model=GEMINI_MODEL, google_api_key=settings.GEMINI_API_KEY,
            )
            result["model"], result["dim"] = model, len(model.embed_query("probe"))
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=_try, daemon=True)
    t.start()
    t.join(PROBE_TIMEOUT_S)

    if t.is_alive():
        _say("warning", f"Gemini probe timed out after {PROBE_TIMEOUT_S}s.")
        return None, None
    if "error" in result:
        _say("warning", f"Gemini probe failed: {result['error']}")
        return None, None
    return result["model"], result["dim"]


def _load_fallback():
    from sentence_transformers import SentenceTransformer
    _say("info", f"Loading local embedding model ({FALLBACK_MODEL}).")
    model = SentenceTransformer(FALLBACK_MODEL)
    get_dim = getattr(model, "get_embedding_dimension", None) \
        or model.get_sentence_embedding_dimension
    return model, get_dim()


def _init():
    global _active_model, _model_type, _dim
    if _active_model is not None:
        return

    _say("info", f"Embedding backend setting: '{_backend_setting}'")

    if _backend_setting == "fallback":
        _active_model, _dim = _load_fallback()
        _model_type = "fallback"
    else:
        model, dim = _probe_gemini()
        if model is not None:
            _active_model, _model_type, _dim = model, "gemini", dim
        elif _backend_setting == "gemini":
            raise RuntimeError("Backend is 'gemini' but the Gemini probe failed (see warning above).")
        else:
            _say("warning", "Falling back to the local model.")
            _active_model, _dim = _load_fallback()
            _model_type = "fallback"

    _say("info", f"Active embedding backend: {_model_type} ({_dim}-dim).")


def switch_to_fallback():
    """Permanently switch this process to the local model (e.g. after a Gemini quota error)."""
    global _active_model, _model_type, _dim, _backend_setting
    _backend_setting = "fallback"
    _active_model, _dim = _load_fallback()
    _model_type = "fallback"
    _say("warning", f"Switched to the local model ({_dim}-dim). Rebuild the collection at this size.")


def get_backend() -> str:
    _init()
    return _model_type


def get_embedding_dim() -> int:
    _init()
    return _dim


# ---------- Gemini rate limiting ----------

def _throttle(n: int):
    """Block until sending n more texts keeps us under the per-minute quota."""
    while True:
        now = time.monotonic()
        while _sent and now - _sent[0][0] > 60:
            _sent.popleft()
        if not _sent or sum(c for _, c in _sent) + n <= GEMINI_MAX_PER_MIN:
            _sent.append((now, n))
            return
        time.sleep(max(60 - (now - _sent[0][0]) + 0.5, 0.5))
        

def _retry_delay(err: str):
    m = re.search(r"retry in ([\d.]+)s", err) or re.search(r"retry.?delay\W+(\d+)", err)
    return float(m.group(1)) if m else None


def _embed_gemini(batch: list[str]) -> list[list[float]]:
    for attempt in range(GEMINI_QUOTA_RETRIES + 1):
        _throttle(len(batch))
        try:
            return _active_model.embed_documents(batch)
        except Exception as e:
            err = str(e).lower()
            if not any(x in err for x in ("429", "resource_exhausted", "quota")):
                raise                                       # real error: surface it
            if "per day" in err or "perday" in err or attempt == GEMINI_QUOTA_RETRIES:
                raise EmbeddingQuotaError("Gemini quota exhausted.") from e
            wait = min((_retry_delay(err) or 5 * 2 ** attempt) + 1, MAX_WAIT_S)
            logfire.warning("Gemini quota hit - waiting {wait}s (attempt {n}/{m})",
                            wait=round(wait), n=attempt + 1, m=GEMINI_QUOTA_RETRIES + 1)
            time.sleep(wait)


# ---------- public API ----------

def _embed_batch(batch: list[str]) -> list[list[float]]:
    if _model_type == "gemini":
        return _embed_gemini(batch)
    return _active_model.encode(batch, show_progress_bar=False).tolist()


def embed_query(query: str) -> list[float]:
    _init()
    if _model_type == "gemini":
        return _active_model.embed_query(query)
    return _active_model.encode([query])[0].tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    _init()
    size = GEMINI_BATCH if _model_type == "gemini" else BATCH_SIZE
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), size):
        batch = texts[i:i + size]
        with logfire.span("Embed batch", model=_model_type, start=i, size=len(batch)):
            all_embeddings.extend(_embed_batch(batch))
    return all_embeddings