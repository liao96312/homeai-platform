import re



# ---------------------------------------------------------------------------
# Text splitting
# ---------------------------------------------------------------------------

def split_text(text: str, chunk_size: int = 800, chunk_overlap: int = 120) -> list[str]:
    chunk_size = max(200, min(chunk_size, 4000))
    chunk_overlap = max(0, min(chunk_overlap, chunk_size // 2))
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(split_long_text(paragraph, chunk_size, chunk_overlap))
            continue
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            chunks.append(current.strip())
            current = merge_overlap(current, paragraph, chunk_overlap)
    if current:
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk]


def split_long_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - chunk_overlap)
    return chunks


def merge_overlap(previous: str, next_text: str, overlap: int) -> str:
    if overlap <= 0:
        return next_text
    suffix = previous[-overlap:].strip()
    return f"{suffix}\n\n{next_text}".strip()

