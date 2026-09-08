from pathlib import Path

from pypdf import PdfReader, PdfWriter


def write_single_page_pdf(reader: PdfReader, page_index: int, output_path: Path):
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])

    with open(output_path, "wb") as f:
        writer.write(f)


def write_merged_pdf(reader: PdfReader, page_numbers: list[int], output_path: Path):
    writer = PdfWriter()

    for page_number in page_numbers:
        writer.add_page(reader.pages[page_number - 1])

    with open(output_path, "wb") as f:
        writer.write(f)
