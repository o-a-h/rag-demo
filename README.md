# When RAG Goes Wrong: Notes from Building a Naive System

I built a basic RAG system over Anthropic's documentation last week to develop hands-on intuition about where these systems actually break. The system was deliberately simple — fixed-size character chunks, OpenAI's `text-embedding-3-large`, Pinecone for storage, top-5 retrieval. No reranking, no hybrid search, no clever chunking. The point wasn't to build something good; it was to see what fails when you don't.

Here's what I found.

## Failure 1: Vocabulary similarity is not relevance

I asked the system *"What's the difference between system prompts and developer messages?"* Developer messages aren't standard Anthropic terminology, but the system returned chunks from the system prompt documentation anyway — because they shared vocabulary with the query, not because they addressed it.

The deeper issue: embedding similarity is a proxy for relevance, not a measure of it. A chunk that mentions "system prompts" and "API" will rank highly for queries about either, even when the actual content is about something else entirely (like rate limits in an API context).

The standard fixes — hybrid retrieval combining vector similarity with BM25 keyword search, or reranking the top 20 results with a dedicated relevance model — exist precisely because pure embedding similarity isn't enough.

## Failure 2: Naive chunking destroys meaning

My chunker split text at 1000-character boundaries with no awareness of sentence or paragraph structure. The retrieved chunks frequently started mid-sentence, in the middle of words like `embed|dings` or in the middle of clauses that depended on previous context to make sense.

When these chunks get passed to an LLM, the model has to either guess at the missing context (often badly) or admit it can't answer. Either way, the user experience degrades.

Fixes are well-known: recursive chunking that respects paragraph and sentence boundaries, chunk overlap so adjacent chunks share content, structured chunking that preserves document hierarchy as metadata. None of this is in basic tutorials but all of it matters for production.

## Failure 3: No notion of "I don't know"

I asked *"What's the population of Boston?"* — a question my corpus has no information about. The system returned five chunks with similarity scores around 0.3–0.4. Lower than for in-corpus queries, but not low enough to trigger any obvious "no results" signal.

This is a structural problem with vector retrieval: there's no objective threshold below which a result is unambiguously irrelevant. Embedding spaces cluster in ways that produce some similarity between almost any pair of texts. Without explicit threshold tuning and "I don't know" handling in the generation step, the system will confidently produce answers for questions outside its scope.

In production, this becomes "hallucination" — but the root cause isn't the LLM making things up. It's retrieval returning irrelevant chunks that the LLM then dutifully uses.

## Failure 4: Quality varies in ways the system can't see

Some queries worked reasonably well. *"How do I use the Messages API?"* returned the right documentation. Others failed in the ways above. The variance itself is the deeper problem — production systems need consistent quality, not "good sometimes."

The fix here isn't a technical change to retrieval. It's evaluation infrastructure. You need a test set of queries with known correct retrievals, automated measurement of how often the system finds them, and continuous monitoring of production query patterns. Without measurement, you can't tell whether changes to the system are helping or hurting.

This is why every serious RAG engagement starts with eval design rather than retrieval optimization.

## The takeaway

Building this took a few hours and used maybe 200 lines of Python. What it produced — concrete, specific intuition about where RAG fails — would have taken weeks of reading to get the same depth of understanding.

If you're considering RAG for a production use case, build the naive version first. Run real queries against it. Look at the failures specifically. The fixes are more obvious once you've felt the failures in your own data.

The companies that get RAG right in production aren't the ones with the most sophisticated initial architecture. They're the ones who measured carefully, iterated based on observed failures, and treated retrieval quality as an ongoing engineering problem rather than a one-time build.

## Reproducing the demo

If you want to build the same system to see the failures firsthand, here's how.

### Prerequisites

- Python 3.10+ with [uv](https://docs.astral.sh/uv/) installed
- A [Pinecone](https://app.pinecone.io) account (free tier works)
- An [OpenAI API key](https://platform.openai.com/api-keys) for embeddings
- An [Anthropic API key](https://console.anthropic.com) (for Phase 3, generation)

### Setup

Clone the repo and install dependencies:

```bash
uv init
uv add openai pinecone anthropic python-dotenv
```

Create a `.env` file in the project root with your API keys:

```
PINECONE_API_KEY=your-pinecone-key
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
```

Add `.env` to `.gitignore` to avoid committing keys.

### Create the Pinecone index

Either through the [Pinecone dashboard](https://app.pinecone.io) or programmatically:

- **Name:** `claude-docs`
- **Dimensions:** `3072` (must match `text-embedding-3-large`)
- **Metric:** `cosine`
- **Capacity:** Serverless, AWS, us-east-1

### Assemble the corpus

Create a `corpus/` directory and add 10–15 markdown or text files. The corpus used for this writeup was:

- 5 pages from docs.claude.com (prompt engineering, system prompts, tool use, Messages API, prompt caching)
- The original RAG paper (Lewis et al. 2020, [arxiv.org/abs/2005.11401](https://arxiv.org/abs/2005.11401))
- 3 of Hamel Husain's eval posts ([hamel.dev](https://hamel.dev))
- 2 of Eugene Yan's production AI writeups ([eugeneyan.com](https://eugeneyan.com))

Save each as a plain `.md` file with a descriptive name.

### Run the indexing pipeline

```bash
uv run python index_corpus.py
```

This reads each file in `corpus/`, splits into 1000-character chunks, embeds each chunk with `text-embedding-3-large`, and upserts to Pinecone with source and chunk-index metadata. Expect 150–250 vectors for a corpus of this size.

### Run queries

```bash
uv run python query.py "How do I set a system prompt in the Anthropic API?"
```

The script embeds the query, retrieves the top 5 most similar chunks from Pinecone, and prints them with similarity scores and source metadata.

### Suggested queries for surfacing failures

Run these and look at the results carefully:

- *"How do I use the Messages API?"* — should work reasonably well (baseline)
- *"What's the difference between system prompts and developer messages?"* — tests vocabulary mismatch
- *"When should I use prompt caching versus prompt engineering?"* — tests cross-document synthesis
- *"What features does Claude not support?"* — tests negation handling
- *"What's the population of Boston?"* — tests behavior on out-of-corpus queries

The failure modes described above will surface in these queries. Looking at the raw chunks (before any LLM smoothing) makes the issues most visible.

### What's deliberately not in the code

The point of this exercise is to see naive RAG fail, not to build a production system. The implementation omits:

- Overlapping chunks (adjacent chunks share no content)
- Sentence-aware or recursive splitting
- Hybrid retrieval (vector + BM25)
- Reranking of top candidates
- Similarity thresholds for "no results"
- Evaluation infrastructure

Each of these is a real fix for the failures observed. Adding them is the next iteration.
