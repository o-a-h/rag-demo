"""
Query the corpus index and print the top retrieved chunks.
Run with: uv run python query.py "your question here"
"""

import os
import sys
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone

load_dotenv()

INDEX_NAME = "claude-docs"
EMBEDDING_MODEL = "text-embedding-3-large"
TOP_K = 5  # Number of chunks to retrieve

openai_client = OpenAI()
pc = Pinecone()
index = pc.Index(INDEX_NAME)


def embed_query(query: str) -> list[float]:
    """Get the embedding for a query string."""
    response = openai_client.embeddings.create(
        input=query,
        model=EMBEDDING_MODEL,
    )
    return response.data[0].embedding


def retrieve(query: str, top_k: int = TOP_K) -> list[dict]:
    """Retrieve the top-k most similar chunks for a query."""
    query_embedding = embed_query(query)
    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        include_metadata=True,
    )
    return results.matches


def main():
    if len(sys.argv) < 2:
        print('Usage: uv run python query.py "your question"')
        sys.exit(1)

    query = sys.argv[1]
    print(f"Query: {query}\n")

    matches = retrieve(query)

    print(f"Top {len(matches)} chunks:\n")
    for i, match in enumerate(matches, 1):
        score = match.score
        source = match.metadata.get("source", "unknown")
        chunk_idx = match.metadata.get("chunk_index", "?")
        text = match.metadata.get("text", "")

        print(f"--- Result {i} (score: {score:.3f}, source: {source}, chunk {chunk_idx}) ---")
        print(text[:500])  # First 500 chars
        if len(text) > 500:
            print(f"... [{len(text) - 500} more chars]")
        print()


if __name__ == "__main__":
    main()
