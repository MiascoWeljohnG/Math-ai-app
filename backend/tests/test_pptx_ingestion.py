import io
from pptx import Presentation
from pptx.util import Inches
import pytest

from classifier import document_text


def _create_sample_pptx():
    prs = Presentation()
    blank_layout = prs.slide_layouts[6]
    
    # Slide 1: Title and content
    slide1 = prs.slides.add_slide(blank_layout)
    txBox = slide1.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    tf = txBox.text_frame
    tf.text = "Introduction to Calculus"
    p2 = tf.add_paragraph()
    p2.text = "Derivatives and Integrals"

    # Slide 2: Table and notes
    slide2 = prs.slides.add_slide(blank_layout)
    table_shape = slide2.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(4), Inches(2))
    table = table_shape.table
    table.cell(0, 0).text = "Function"
    table.cell(0, 1).text = "Derivative"
    table.cell(1, 0).text = "x^2"
    table.cell(1, 1).text = "2x"

    notes_slide = slide2.notes_slide
    notes_slide.notes_text_frame.text = "Remember the power rule."

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_pptx_text_extraction_real_rag(monkeypatch):
    import importlib.util
    import pathlib
    rag_path = pathlib.Path(__file__).resolve().parent.parent / "rag.py"
    spec = importlib.util.spec_from_file_location("real_rag", rag_path)
    real_rag = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real_rag)

    data = _create_sample_pptx()
    pages = real_rag.extract_text_from_bytes("sample.pptx", data)
    assert len(pages) == 2

    # Check slide 1 content
    s1_num, s1_text, s1_tables = pages[0]
    assert s1_num == 1
    assert "Introduction to Calculus" in s1_text
    assert "Derivatives and Integrals" in s1_text

    # Check slide 2 table and notes
    s2_num, s2_text, s2_tables = pages[1]
    assert s2_num == 2
    assert "Remember the power rule." in s2_text
    assert len(s2_tables) == 1
    assert "| Function | Derivative |" in s2_tables[0]
    assert "| x^2 | 2x |" in s2_tables[0]

    # Also test classifier document_text against real_rag
    monkeypatch.setattr("rag.extract_text_from_bytes", real_rag.extract_text_from_bytes)
    full_text = document_text("sample.pptx", data)
    assert "Introduction to Calculus" in full_text
    assert "Derivatives and Integrals" in full_text
    assert "Remember the power rule." in full_text

