"""
Index the corpus directory into Pinecone.
Run with: uv run python index_corpus.py
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone

load_dotenv()

# Configuration
CORPUS_DIR = Path("corpus")
INDEX_NAME = "claude-docs"  # Match what you created in Pinecone dashboard
EMBEDDING_MODEL = "text-embedding-3-large"
CHUNK_SIZE = 1000  # characters per chunk
EMBEDDING_BATCH_SIZE = 50  # chunks per embedding API call
UPSERT_BATCH_SIZE = 100  # vectors per Pinecone upsert call

# Initialize clients
openai_client = OpenAI()
pc = Pinecone()

from pinecone import ServerlessSpec

# Create index if it doesn't exist
existing_indexes = [idx.name for idx in pc.list_indexes()]
if INDEX_NAME not in existing_indexes:
    print(f"Creating index '{INDEX_NAME}'...")
    pc.create_index(
        name=INDEX_NAME,
        dimension=3072,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    # Wait for it to be ready
    import time
    while not pc.describe_index(INDEX_NAME).status["ready"]:
        time.sleep(1)
    print("Index created and ready.")


index = pc.Index(INDEX_NAME)

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into fixed-size character chunks. Naive approach — no overlap, no sentence awareness."""
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size].strip()
        if chunk:  # Skip empty chunks
            chunks.append(chunk)
    return chunks


def load_corpus(corpus_dir: Path) -> list[dict]:
    """Load all files from corpus directory, chunk them, return list of chunk records."""
    records = []
    for file_path in sorted(corpus_dir.glob("*.md")):
        text = file_path.read_text(encoding="utf-8", errors="replace")
        chunks = chunk_text(text)
        for chunk_index, chunk in enumerate(chunks):
            records.append({
                "id": f"{file_path.stem}-{chunk_index}",
                "text": chunk,
                "source": file_path.name,
                "chunk_index": chunk_index,
            })
        print(f"  {file_path.name}: {len(chunks)} chunks")
    return records


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Get embeddings for a batch of texts."""
    response = openai_client.embeddings.create(
        input=texts,
        model=EMBEDDING_MODEL,
    )
    return [item.embedding for item in response.data]


def main():
    print("Loading corpus...")
    records = load_corpus(CORPUS_DIR)
    print(f"\nTotal chunks: {len(records)}\n")

    print("Generating embeddings...")
    # Embed in batches
    for batch_start in range(0, len(records), EMBEDDING_BATCH_SIZE):
        batch = records[batch_start:batch_start + EMBEDDING_BATCH_SIZE]
        texts = [r["text"] for r in batch]
        embeddings = embed_batch(texts)
        for record, embedding in zip(batch, embeddings):
            record["embedding"] = embedding
        print(f"  Embedded {batch_start + len(batch)}/{len(records)}")

    print("\nUpserting to Pinecone...")
    # Upsert in batches
    for batch_start in range(0, len(records), UPSERT_BATCH_SIZE):
        batch = records[batch_start:batch_start + UPSERT_BATCH_SIZE]
        vectors = [
            {
                "id": r["id"],
                "values": r["embedding"],
                "metadata": {
                    "text": r["text"],
                    "source": r["source"],
                    "chunk_index": r["chunk_index"],
                }
            }
            for r in batch
        ]
        index.upsert(vectors=vectors)
        print(f"  Upserted {batch_start + len(batch)}/{len(records)}")

    print("\nDone. Verify in Pinecone dashboard.")


if __name__ == "__main__":
    main()
