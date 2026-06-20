from docx import Document
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from app.exception_handling_layer.exception_handling import FileParsingException


def iter_block_items(parent):
    """
    Yield each paragraph and table in the *parent*, in document order.
    Each returned value is an instance of either Table or Paragraph.
    """
    if str(type(parent)) == "<class 'docx.document.Document'>":
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise ValueError("something's not right")

    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            para = Paragraph(child, parent)
            if para.style.name.startswith('Heading'):
                yield ('Heading', para)
            else:
                yield ('Paragraph', para)
        elif isinstance(child, CT_Tbl):
            yield ('Table', Table(child, parent))

def process_document(doc_path):
    """
    This function reads a Word document, identifies sections based on heading styles,
    and collects the content under each heading, including paragraphs and tables.
    Args:
        doc_path: Path to the Word document to be processed.
    Return:
        A list of dictionaries, each containing a section header and its content.
    """
    try:
        doc = Document(doc_path)
        sections = []
        current_section = None

        for item_type, item in iter_block_items(doc):
            if item_type == 'Heading':
                # Start a new section
                current_section = item.text.strip()
                if current_section:
                    last_heading = ""
                    if sections and len(sections[-1]['header_content'].strip()) == 0:
                        last_heading = sections[-1]['header'] + " : "
                        sections.pop()
                    sections.append({'header': last_heading + current_section, 'header_content': ""})
            elif current_section is not None:
                # Add the item to the current section
                if isinstance(item, Paragraph):
                    sections[-1]['header_content'] += item.text.strip() + " "
                elif isinstance(item, Table):
                    for row in item.rows:
                        row_text = ' | '.join(
                            ' '.join(paragraph.text.strip() for paragraph in cell.paragraphs) for cell in row.cells)
                        sections[-1]['header_content'] += row_text + "\n"
        return sections

    except Exception as e:
        raise FileParsingException("There is an issue with your Word document. Please recheck your file and try uploading again")

