from django.db.models import Q

from .models import KnowledgeChunk


def build_knowledge_context(chunks):
    """Include continuations so legacy fixed-width excerpts do not cut facts off."""
    if not chunks:
        return ""
    following = Q()
    for chunk in chunks:
        following |= Q(source_id=chunk.source_id, chunk_index=chunk.chunk_index + 1)
    continuations = {
        (chunk.source_id, chunk.chunk_index): chunk.content
        for chunk in KnowledgeChunk.objects.filter(following, source__status="ready")
    }
    blocks = []
    for chunk in chunks:
        content = chunk.content
        continuation = continuations.get((chunk.source_id, chunk.chunk_index + 1), "")
        if continuation:
            # Join overlapping excerpts without inserting a break inside a number.
            overlap = next((size for size in range(min(len(content), len(continuation)), 0, -1)
                            if content[-size:] == continuation[:size]), 0)
            content += continuation[overlap:] if overlap else "\n" + continuation
        blocks.append(f"[Source: {chunk.source.title}]\n{content}")
    return "\n\n".join(blocks)
