import re

from .url_extraction import extract_text_from_url
from django.db import transaction

from .document_extraction import extract_text_from_file
from .models import KnowledgeChunk, KnowledgeSource


def split_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 100,
) -> list[str]:
    """Split text into overlapping character-based chunks."""

    if not text or not text.strip():
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be non-negative and smaller than chunk_size"
        )

    text = text.strip()
    step = chunk_size - overlap
    chunks = []

    # Keep phone-like numeric sequences intact, including spaces and hyphens.
    numbers = list(re.finditer(r"\+?\d(?:[\d ()/.-]{0,48}\d)?", text))

    for start in range(0, len(text), step):
        end = min(start + chunk_size, len(text))
        for number in numbers:
            if number.start() < start < number.end():
                start = number.start()
            if number.start() < end < number.end():
                end = number.end()
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

    return chunks


@transaction.atomic
def create_source_chunks(source: KnowledgeSource) -> int:
    """
    Extract text from a supported source, save overlapping chunks,
    and mark the source as ready.
    """

    if source.source_type == KnowledgeSource.SourceType.TEXT:
        extracted_text = source.text_content

    elif source.source_type == KnowledgeSource.SourceType.FILE:
        if not source.file:
            raise ValueError("File source has no uploaded file.")
        extracted_text = extract_text_from_file(source.file.path)

    elif source.source_type == KnowledgeSource.SourceType.URL:
        if not source.source_url:
            raise ValueError("URL source has no website URL.")
        extracted_text = extract_text_from_url(source.source_url)

    else:
        raise ValueError("Unsupported knowledge source type.")

    chunks = split_text(extracted_text)

    if not chunks:
        raise ValueError(
            "Cannot create chunks because the source contains no readable text."
        )

    # Replace existing chunks only after extraction and chunking succeed.
    KnowledgeChunk.objects.filter(source=source).delete()

    KnowledgeChunk.objects.bulk_create(
        [
            KnowledgeChunk(
                source=source,
                content=content,
                chunk_index=index,
            )
            for index, content in enumerate(chunks)
        ]
    )

    source.status = KnowledgeSource.Status.READY
    source.error_message = ""
    source.save(update_fields=["status", "error_message", "updated_at"])

    return len(chunks)
