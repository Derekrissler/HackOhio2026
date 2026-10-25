"""Quotes from slides and notes shown in the chat. Only text that really appears in retrieved material survives.

The model proposes quotes; the server finds each one in the chunk it claims to come from (ignoring case, spacing
and curly vs straight quotes) and shows the chunk's own text for that span, line breaks included.
"""

from dataclasses import dataclass

from tutor.models import Chunk, Snippet

MAX_SNIPPETS = 3
MAX_SNIPPET_CHARS = 500
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


@dataclass(frozen=True)
class ShownSnippet:
    chunk: Chunk
    text: str  # exactly as it appears in the chunk


def _normalized(text: str) -> tuple[str, list[int]]:
    """Lowercased, quote-straightened, whitespace-collapsed text, plus each character's index in the original."""
    out, index, pending_space = [], [], False
    for i, ch in enumerate(text.translate(_QUOTES)):
        if ch.isspace():
            pending_space = bool(out)
            continue
        if pending_space:
            out.append(" ")
            index.append(i - 1)
            pending_space = False
        low = ch.lower()
        out.append(low if len(low) == 1 else ch)
        index.append(i)
    return "".join(out), index


def select_snippets(proposed: list[Snippet], chunks: dict[str, Chunk]) -> tuple[list[ShownSnippet], list[str]]:
    kept, dropped, seen = [], [], set()
    for s in proposed:
        chunk = chunks.get(s.chunk_id)
        if chunk is None:
            dropped.append(f"{s.chunk_id}: material was not retrieved")
            continue
        quote = _normalized(s.quote)[0]
        content, index = _normalized(chunk.content)
        pos = content.find(quote) if quote else -1
        if pos < 0:
            dropped.append(f"{s.chunk_id}: quote not found in the material")
            continue
        text = chunk.content[index[pos]:index[pos + len(quote) - 1] + 1]
        if len(text) > MAX_SNIPPET_CHARS:
            dropped.append(f"{s.chunk_id}: quote too long")
        elif (chunk.id, text) not in seen and len(kept) < MAX_SNIPPETS:
            seen.add((chunk.id, text))
            kept.append(ShownSnippet(chunk, text))
    return kept, dropped
