
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from docx import Document
from pypdf import PdfWriter

from knowledge.document_extraction import extract_text_from_file


class DocumentExtractionTests(SimpleTestCase):
    def create_temp_file(self, suffix, content):
        temporary_file = tempfile.NamedTemporaryFile(
            suffix=suffix,
            delete=False,
        )
        temporary_file.write(content)
        temporary_file.close()

        self.addCleanup(Path(temporary_file.name).unlink, missing_ok=True)
        return temporary_file.name

    def test_extracts_text_from_txt_file(self):
        content = "SRM Nursing College admission information."
        file_path = self.create_temp_file(".txt", content.encode("utf-8"))

        extracted_text = extract_text_from_file(file_path)

        self.assertEqual(extracted_text, content)

    def test_extracts_text_from_markdown_file(self):
        content = "# Nursing Admissions\nEligibility information."
        file_path = self.create_temp_file(".md", content.encode("utf-8"))

        extracted_text = extract_text_from_file(file_path)

        self.assertEqual(extracted_text, content)

    def test_extracts_text_from_docx_file(self):
        with tempfile.NamedTemporaryFile(
            suffix=".docx",
            delete=False,
        ) as temporary_file:
            file_path = temporary_file.name

        self.addCleanup(Path(file_path).unlink, missing_ok=True)

        document = Document()
        document.add_paragraph("Nursing admission information.")
        document.save(file_path)

        extracted_text = extract_text_from_file(file_path)

        self.assertIn("Nursing admission information.", extracted_text)

    def test_rejects_unsupported_file_type(self):
        file_path = self.create_temp_file(".exe", b"test content")

        with self.assertRaises(ValueError):
            extract_text_from_file(file_path)

    def test_rejects_missing_file(self):
        file_path = str(Path(tempfile.gettempdir()) / "missing_knowledge_test.txt")

        with self.assertRaises(FileNotFoundError):
            extract_text_from_file(file_path)

    def test_rejects_empty_text_file(self):
        file_path = self.create_temp_file(".txt", b"   \n\t")

        with self.assertRaises(ValueError):
            extract_text_from_file(file_path)


    def test_extracts_text_from_pdf_file(self):
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        with tempfile.NamedTemporaryFile(
            suffix=".pdf",
            delete=False,
        ) as temporary_file:
            file_path = temporary_file.name

        self.addCleanup(Path(file_path).unlink, missing_ok=True)

        pdf = canvas.Canvas(file_path, pagesize=letter)
        pdf.drawString(100, 750, "Nursing admission information.")
        pdf.save()

        extracted_text = extract_text_from_file(file_path)

        self.assertIn("Nursing admission information.", extracted_text)
