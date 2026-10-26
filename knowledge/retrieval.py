import re
from collections import Counter
from math import log

from .models import KnowledgeChunk

STOP_WORDS = frozenset('a an the is are was were be been being i me my we our you your it its this that these those of for to in on at by with from and or but do does did can could would should please tell about what which who how'.split())


def tokenize(text: str) -> set[str]:
    """Normalize common English plurals and ignore non-informative words."""
    words = set(re.findall(r'\b\w+\b', text.casefold())) - STOP_WORDS
    normalized = set()
    for word in words:
        if len(word) > 4 and word.endswith('ies'):
            word = word[:-3] + 'y'
        elif len(word) > 3 and word.endswith('s') and not word.endswith(('ss', 'us', 'is')):
            word = word[:-1]
        normalized.add(word)
    return normalized


def retrieve_relevant_chunks(agent_id: int, query: str, limit: int = 5) -> list:
    """Search every ready source for this agent, then diversify the context.

    Titles make a source such as "Events" discoverable even when individual
    entries only name a seminar or workshop. Rare matching terms outweigh
    boilerplate. Select the best chunk from each matching source before filling
    remaining slots, so a large source cannot crowd out all other sources.
    Unrelated sources and other agents' data are never used as fallback.
    """
    if not query or not query.strip() or limit < 1:
        return []
    query_tokens = tokenize(query)
    # Time qualifiers alone must not pull in unrelated topics (for example,
    # "latest admission notification" when the question is "latest event").
    topical_tokens = query_tokens - {'latest', 'recent', 'new', 'current', 'upcoming', 'next'}
    if topical_tokens:
        query_tokens = topical_tokens
    if not query_tokens:
        return []
    chunks = list(KnowledgeChunk.objects.filter(
        source__agent_id=agent_id, source__status='ready',
    ).select_related('source'))
    if not chunks:
        return []
    documents = [(chunk, tokenize(chunk.content), tokenize(chunk.source.title)) for chunk in chunks]
    frequencies = Counter(token for _, content, title in documents for token in content | title)
    weights = {token: 1 + log((len(chunks) + 1) / (frequencies[token] + 1)) for token in query_tokens}
    scored = []
    for chunk, content, title in documents:
        score = sum(weights[token] for token in query_tokens & content)
        score += sum(2 * weights[token] for token in query_tokens & title)
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: (-item[0], item[1].source_id, item[1].chunk_index, item[1].pk))
    selected, remaining, seen_sources = [], [], set()
    for _, chunk in scored:
        if chunk.source_id not in seen_sources:
            selected.append(chunk)
            seen_sources.add(chunk.source_id)
        else:
            remaining.append(chunk)
    return (selected + remaining)[:limit]
