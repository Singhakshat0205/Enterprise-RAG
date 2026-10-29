from typing import List

import logfire
from langchain_text_splitters import RecursiveCharacterTextSplitter

# all-mpnet-base-v2 reads ~384 tokens (~1500 chars), so 1000 chars stays safely inside it
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks, preferring paragraph, line, then sentence boundaries."""
    with logfire.span("Text Chunking", text_length=len(text)):
        if not text or not text.strip():
            return []

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        chunks = [c.strip() for c in splitter.split_text(text) if c.strip()]
        logfire.info("Generated {n} chunks", n=len(chunks))
        return chunks