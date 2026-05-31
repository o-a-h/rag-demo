#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
#     "trafilatura>=1.12",
# ]
# ///
"""
Build the RAG corpus.

Fetches each URL in DOCS, extracts the main article text with trafilatura,
and writes it as a plain-text markdown file under corpus/.

Usage:
    uv run scripts/build_corpus.py            # fetch only missing files
    uv run scripts/build_corpus.py --force    # refetch everything
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import trafilatura

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) corpus-builder/0.1"
)


@dataclass(frozen=True)
class Doc:
    slug: str
    url: str
    source: str  # short label for the header


DOCS: list[Doc] = [
    # Anthropic / Claude docs
    Doc(
        "claude_prompt_engineering_overview",
        "https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/overview",
        "Anthropic docs",
    ),
    Doc(
        "claude_system_prompts",
        "https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/system-prompts",
        "Anthropic docs",
    ),
    Doc(
        "claude_tool_use_overview",
        "https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview",
        "Anthropic docs",
    ),
    Doc(
        "claude_messages_api",
        "https://docs.claude.com/en/api/messages",
        "Anthropic docs",
    ),
    Doc(
        "claude_prompt_caching",
        "https://docs.claude.com/en/docs/build-with-claude/prompt-caching",
        "Anthropic docs",
    ),
    # Foundational paper
    Doc(
        "lewis_2020_rag",
        "https://arxiv.org/abs/2005.11401",
        "arXiv",
    ),
    # Hamel Husain — evals
    Doc(
        "hamel_your_ai_needs_evals",
        "https://hamel.dev/blog/posts/evals/",
        "hamel.dev",
    ),
    Doc(
        "hamel_evals_faq",
        "https://hamel.dev/blog/posts/evals-faq/",
        "hamel.dev",
    ),
    Doc(
        "hamel_eval_tools",
        "https://hamel.dev/blog/posts/eval-tools/",
        "hamel.dev",
    ),
    # Eugene Yan — production LLM patterns
    Doc(
        "yan_llm_patterns",
        "https://eugeneyan.com/writing/llm-patterns/",
        "eugeneyan.com",
    ),
    Doc(
        "yan_eval_process",
        "https://eugeneyan.com/writing/eval-process/",
        "eugeneyan.com",
    ),
]


def fetch(client: httpx.Client, url: str) -> str:
    # docs.claude.com (Mintlify) serves a clean markdown source at URL + ".md".
    # Use that path — its API reference pages are JS-rendered and trafilatura
    # cannot extract content from the rendered HTML.
    if "docs.claude.com" in url:
        md_url = url.rstrip("/") + ".md"
        resp = client.get(md_url, follow_redirects=True, timeout=30)
        resp.raise_for_status()
        text = resp.text.strip()
    else:
        resp = client.get(url, follow_redirects=True, timeout=30)
        resp.raise_for_status()
        text = trafilatura.extract(
            resp.text,
            include_comments=False,
            include_tables=True,
            include_links=False,
            favor_recall=True,
        )
        text = (text or "").strip()

    if len(text) < 200:
        raise ValueError(f"extracted text too short ({len(text)} chars)")
    return text


def write_doc(doc: Doc, body: str) -> Path:
    out = CORPUS / f"{doc.slug}.md"
    fetched = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = (
        f"# {doc.slug}\n\n"
        f"Source: {doc.source} — {doc.url}\n"
        f"Fetched: {fetched}\n\n"
        f"---\n\n"
    )
    out.write_text(header + body + "\n")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="refetch even if file exists")
    args = parser.parse_args()

    CORPUS.mkdir(exist_ok=True)

    failures: list[tuple[str, str]] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for doc in DOCS:
            out = CORPUS / f"{doc.slug}.md"
            if out.exists() and not args.force:
                print(f"skip   {doc.slug}  (exists)")
                continue
            try:
                body = fetch(client, doc.url)
            except Exception as e:
                print(f"FAIL   {doc.slug}: {e}", file=sys.stderr)
                failures.append((doc.slug, str(e)))
                continue
            path = write_doc(doc, body)
            print(f"saved  {doc.slug}  ({len(body):>6} chars)  -> {path.relative_to(ROOT)}")

    print()
    print(f"Wrote {len(DOCS) - len(failures)} / {len(DOCS)} documents to {CORPUS.relative_to(ROOT)}/")
    if failures:
        print("Failures:")
        for slug, err in failures:
            print(f"  - {slug}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
