
import re

from django.db.models import QuerySet

from .models import KnowledgeChunk


def tokenize(text: str) -> set[str]:
    """Convert text into a set of lowercase searchable words."""
    return set(re.findall(r"\b[a-zA-Z0-9]+\b", text.lower()))


def retrieve_relevant_chunks(
    agent_id: int,
    query: str,
    limit: int = 5,
) -> QuerySet | list:
    """
    Return relevant knowledge chunks belonging only to the given agent.

    Only chunks from successfully processed knowledge sources are eligible.
    Results are ordered by keyword overlap, then original chunk order.
    """
    if not query or not query.strip():
        return []

    if limit < 1:
        return []

    query_tokens = tokenize(query)

    if not query_tokens:
        return []

    chunks = (
        KnowledgeChunk.objects.filter(
            source__agent_id=agent_id,
            source__status="ready",
        )
        .select_related("source", "source__agent")
    )

    scored_chunks = []

    for chunk in chunks:
        content_tokens = tokenize(chunk.content)
        score = len(query_tokens & content_tokens)

        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(
        key=lambda item: (
            -item[0],
            item[1].source_id,
            item[1].chunk_index,
        )
    )

    return [chunk for _, chunk in scored_chunks[:limit]]
