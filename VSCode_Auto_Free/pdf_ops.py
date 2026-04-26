from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import fitz


@dataclass(frozen=True)
class PDFPageRef:
    source_path: str
    page_index: int
    page_label: str


class PDFOpsError(Exception):
    pass


def load_pages_from_pdf(path: str) -> list[PDFPageRef]:
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise PDFOpsError(f"File not found: {path}")

    refs: list[PDFPageRef] = []
    with fitz.open(pdf_path) as doc:
        for page_index in range(doc.page_count):
            refs.append(
                PDFPageRef(
                    source_path=str(pdf_path),
                    page_index=page_index,
                    page_label=f"{pdf_path.name} - Page {page_index + 1}",
                )
            )
    return refs


def render_thumbnail(path: str, page_index: int, max_size: tuple[int, int] = (180, 240)) -> fitz.Pixmap:
    with fitz.open(path) as doc:
        page = doc.load_page(page_index)
        rect = page.rect
        scale = min(max_size[0] / rect.width, max_size[1] / rect.height)
        matrix = fitz.Matrix(scale, scale)
        return page.get_pixmap(matrix=matrix, alpha=False)


def save_pages_as_pdf(page_refs: Sequence[PDFPageRef], output_path: str) -> None:
    if not page_refs:
        raise PDFOpsError("No pages selected.")

    output = fitz.open()
    try:
        for ref in page_refs:
            with fitz.open(ref.source_path) as src:
                output.insert_pdf(src, from_page=ref.page_index, to_page=ref.page_index)
        output.save(output_path)
    finally:
        output.close()


def extract_selected_pages(page_refs: Sequence[PDFPageRef], selected_indexes: Iterable[int], output_path: str) -> None:
    selected = [page_refs[index] for index in sorted(set(selected_indexes))]
    save_pages_as_pdf(selected, output_path)


def split_to_individual_pages(page_refs: Sequence[PDFPageRef], output_dir: str, base_name: str) -> list[str]:
    if not page_refs:
        raise PDFOpsError("No pages to split.")

    saved_files: list[str] = []
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    for index, ref in enumerate(page_refs, start=1):
        output_path = output_root / f"{base_name}_page_{index:03d}.pdf"
        save_pages_as_pdf([ref], str(output_path))
        saved_files.append(str(output_path))

    return saved_files


def split_by_ranges(page_refs: Sequence[PDFPageRef], ranges: Sequence[tuple[int, int]], output_dir: str, base_name: str) -> list[str]:
    if not page_refs:
        raise PDFOpsError("No pages to split.")

    saved_files: list[str] = []
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    for index, (start, end) in enumerate(ranges, start=1):
        chunk = page_refs[start : end + 1]
        output_path = output_root / f"{base_name}_part_{index:03d}.pdf"
        save_pages_as_pdf(chunk, str(output_path))
        saved_files.append(str(output_path))

    return saved_files


def parse_page_ranges(text: str, max_pages: int) -> list[tuple[int, int]]:
    if not text.strip():
        raise PDFOpsError("Enter at least one page range.")

    ranges: list[tuple[int, int]] = []
    for raw_part in text.split(","):
        part = raw_part.strip()
        if not part:
            continue

        if "-" in part:
            start_text, end_text = part.split("-", maxsplit=1)
            if not start_text.isdigit() or not end_text.isdigit():
                raise PDFOpsError(f"Invalid range: {part}")
            start = int(start_text)
            end = int(end_text)
        else:
            if not part.isdigit():
                raise PDFOpsError(f"Invalid page number: {part}")
            start = end = int(part)

        if start < 1 or end < 1 or start > end or end > max_pages:
            raise PDFOpsError(f"Out-of-range pages: {part}")
        ranges.append((start - 1, end - 1))

    if not ranges:
        raise PDFOpsError("Enter valid page ranges.")

    return ranges
