import fitz
from pathlib import Path


class DocumentExtractionError(Exception):
    """Raised when a PDF cannot be extracted successfully."""
    pass


def extract_pdf_text(pdf_path: str) -> str:
    """
    Extract text from a supplier RFP PDF using PyMuPDF.

    Parameters
    ----------
    pdf_path : str
        Path to the supplier PDF.

    Returns
    -------
    str
        Cleaned text extracted from the PDF.

    Raises
    ------
    DocumentExtractionError
        If the file does not exist, cannot be opened,
        contains no extractable text, or extraction fails.
    """

    path = Path(pdf_path)

    # -----------------------------------------------------
    # 1. Check that the file exists
    # -----------------------------------------------------

    if not path.exists():
        raise DocumentExtractionError(
            f"PDF file not found: {pdf_path}"
        )

    if not path.is_file():
        raise DocumentExtractionError(
            f"Path is not a file: {pdf_path}"
        )

    # -----------------------------------------------------
    # 2. Check file extension
    # -----------------------------------------------------

    if path.suffix.lower() != ".pdf":
        raise DocumentExtractionError(
            f"Expected a PDF file, received: {path.suffix}"
        )

    # -----------------------------------------------------
    # 3. Open PDF
    # -----------------------------------------------------

    try:
        document = fitz.open(pdf_path)
    except Exception as exc:
        raise DocumentExtractionError(
            f"Unable to open PDF: {exc}"
        ) from exc

    # -----------------------------------------------------
    # 4. Extract text page by page
    # -----------------------------------------------------

    pages = []

    try:

        for page_number, page in enumerate(document, start=1):

            text = page.get_text("text")

            if text:
                text = clean_text(text)

                if text:
                    pages.append(
                        f"\n--- PAGE {page_number} ---\n"
                        f"{text}"
                    )

    except Exception as exc:
        raise DocumentExtractionError(
            f"Error extracting PDF text: {exc}"
        ) from exc

    finally:
        document.close()

    # -----------------------------------------------------
    # 5. Combine pages
    # -----------------------------------------------------

    full_text = "\n".join(pages).strip()

    # -----------------------------------------------------
    # 6. Validate extraction
    # -----------------------------------------------------

    if not full_text:
        raise DocumentExtractionError(
            "No extractable text was found in the PDF."
        )

    return full_text


def clean_text(text: str) -> str:
    """
    Perform basic text cleaning.

    We intentionally keep this conservative because
    the original proposal wording is evidence for the LLM.
    """

    # Normalize line endings
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Remove excessive spaces
    lines = []

    for line in text.split("\n"):

        line = " ".join(line.split())

        if line:
            lines.append(line)

    # Preserve paragraph/page structure
    return "\n".join(lines)


def get_pdf_metadata(pdf_path: str) -> dict:
    """
    Return basic metadata about the PDF.
    """

    path = Path(pdf_path)

    if not path.exists():
        raise DocumentExtractionError(
            f"PDF file not found: {pdf_path}"
        )

    try:
        document = fitz.open(pdf_path)

        metadata = {
            "file_name": path.name,
            "page_count": len(document),
            "file_size_bytes": path.stat().st_size,
            "title": document.metadata.get("title"),
            "author": document.metadata.get("author"),
        }

        document.close()

        return metadata

    except Exception as exc:
        raise DocumentExtractionError(
            f"Unable to read PDF metadata: {exc}"
        ) from exc


if __name__ == "__main__":

    # -----------------------------------------------------
    # Simple standalone test
    # -----------------------------------------------------

    test_pdf = "rfps/apex_systems.pdf"

    try:

        text = extract_pdf_text(test_pdf)

        print("=" * 80)
        print("PDF EXTRACTION TEST")
        print("=" * 80)

        print(f"Characters extracted: {len(text)}")

        print("\nFirst 3000 characters:\n")
        print(text[:3000])

        print("\n" + "=" * 80)

        metadata = get_pdf_metadata(test_pdf)

        print("PDF METADATA")
        print("=" * 80)

        for key, value in metadata.items():
            print(f"{key}: {value}")

    except DocumentExtractionError as exc:

        print(f"\nERROR: {exc}")