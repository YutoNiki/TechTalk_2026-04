"""
pdf_operations.py - Core PDF processing logic using PyMuPDF (fitz)
"""
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Optional, Tuple
import tempfile
import os


def load_pdf(path: str) -> fitz.Document:
    """Open and return a PDF document."""
    return fitz.open(path)


def render_page_thumbnail(doc: fitz.Document, page_index: int, width: int = 150) -> bytes:
    """
    Render a page as a PNG thumbnail and return the raw bytes.
    Scales the page so its width matches `width` pixels.
    """
    page = doc.load_page(page_index)
    # Calculate scale factor
    rect = page.rect
    scale = width / rect.width if rect.width > 0 else 1.0
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def merge_pdfs(input_paths: List[str], output_path: str) -> None:
    """
    Merge multiple PDF files into a single output PDF.
    Pages are appended in the order given by input_paths.
    """
    result = fitz.open()
    for path in input_paths:
        doc = fitz.open(path)
        result.insert_pdf(doc)
        doc.close()
    result.save(output_path, garbage=4, deflate=True)
    result.close()


def merge_pdfs_with_order(
    page_sources: List[Tuple[str, int]],
    output_path: str,
) -> None:
    """
    Merge pages from potentially different PDFs in a custom order.

    Args:
        page_sources: List of (pdf_path, page_index) tuples in desired order.
        output_path: Where to save the merged result.
    """
    # Cache open documents to avoid reopening the same file repeatedly
    docs: dict[str, fitz.Document] = {}
    result = fitz.open()

    for pdf_path, page_index in page_sources:
        if pdf_path not in docs:
            docs[pdf_path] = fitz.open(pdf_path)
        doc = docs[pdf_path]
        result.insert_pdf(doc, from_page=page_index, to_page=page_index)

    for doc in docs.values():
        doc.close()

    result.save(output_path, garbage=4, deflate=True)
    result.close()


def split_pdf_by_page(input_path: str, output_dir: str) -> List[str]:
    """
    Split each page of the input PDF into its own file.
    Files are named <original_stem>_page_001.pdf etc.
    Returns the list of created file paths.
    """
    doc = fitz.open(input_path)
    stem = Path(input_path).stem
    output_paths = []

    for i in range(len(doc)):
        out_doc = fitz.open()
        out_doc.insert_pdf(doc, from_page=i, to_page=i)
        out_path = str(Path(output_dir) / f"{stem}_page_{i + 1:03d}.pdf")
        out_doc.save(out_path, garbage=4, deflate=True)
        out_doc.close()
        output_paths.append(out_path)

    doc.close()
    return output_paths


def split_pdf_by_ranges(
    input_path: str,
    ranges: List[Tuple[int, int]],
    output_dir: str,
) -> List[str]:
    """
    Split a PDF into multiple files according to page ranges.

    Args:
        input_path: Source PDF path.
        ranges: List of (start, end) tuples (0-indexed, inclusive).
        output_dir: Directory to save split files.

    Returns:
        List of created output file paths.
    """
    doc = fitz.open(input_path)
    stem = Path(input_path).stem
    output_paths = []

    for idx, (start, end) in enumerate(ranges):
        out_doc = fitz.open()
        out_doc.insert_pdf(doc, from_page=start, to_page=end)
        out_path = str(Path(output_dir) / f"{stem}_part_{idx + 1:03d}.pdf")
        out_doc.save(out_path, garbage=4, deflate=True)
        out_doc.close()
        output_paths.append(out_path)

    doc.close()
    return output_paths


def delete_pages(input_path: str, page_indices: List[int], output_path: str) -> None:
    """
    Remove specified pages (0-indexed) from the PDF and save the result.
    """
    doc = fitz.open(input_path)
    # delete_page works from the end to avoid index shifting
    for idx in sorted(page_indices, reverse=True):
        doc.delete_page(idx)
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()


def extract_pages(input_path: str, page_indices: List[int], output_path: str) -> None:
    """
    Extract specific pages (0-indexed) from the PDF and save them.
    """
    doc = fitz.open(input_path)
    result = fitz.open()
    for idx in sorted(page_indices):
        result.insert_pdf(doc, from_page=idx, to_page=idx)
    doc.close()
    result.save(output_path, garbage=4, deflate=True)
    result.close()
