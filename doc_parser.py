import os
from docx import Document
from typing import List, Dict
from transformers import AutoTokenizer, AutoModelForTokenClassification
from app.Utilities.WordParserUtilities import Utilities
from app.exception_handling_layer.exception_handling import FileParsingException
from app.file_parsing_layer.word_parser.VisionDocumentParser import TextDocumentParser
from app.file_parsing_layer.word_parser.WordDocumentTableParser import process_document


class WordParser:
    """
    A class to parse Word and PDF documents, extract headings and content, and convert them into a specific format.
    """
    def __init__(self):
        self.file_path = ""
        self.file_name = ""
        self.model_id = "pierreguillou/lilt-xlm-roberta-base-finetuned-with-DocLayNet-base-at-linelevel-ml384"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id,cache_dir=os.path.join(os.getenv('ADVISORY_MODELS'), "Model"))
        self.model = AutoModelForTokenClassification.from_pretrained(self.model_id,cache_dir=os.path.join(os.getenv('ADVISORY_MODELS'), "Model"))

    def set_file_name(self):
        return os.path.basename(self.file_path)

    def return_heading_count(self, doc):
        """
        Counts the number of headings in a Word document.
        """
        try:
            heading_count = 0
            for paragraph in doc.paragraphs:
                if paragraph.style.name.startswith('Heading'):
                    heading_count += 1
            return heading_count
        except Exception as e:
            raise FileParsingException("There is an issue in number of heading count in a word file")

    def word_parser(self, file_path):
        """
        Parses a Word or PDF document, extracts headings and content, and converts them into a specific format.
        Args:
            file_path: Path to the document to be parsed.
        Return: List of Parsed data.
        """
        try:
            self.file_path = file_path
            self.file_name = self.set_file_name()
            if self.file_name.endswith('.pdf'):
                pdf_parser = TextDocumentParser(self.model, self.tokenizer)
                model_parsed_df_list = pdf_parser.pdf_processor(file_path)
                model_parsed_df = pdf_parser.combine_datasets(model_parsed_df_list)
                parser_format_data = pdf_parser.df_to_parser_format(model_parsed_df, file_path)
                return parser_format_data

            elif self.file_name.endswith('.docx'):
                doc = Document(self.file_path)

            else:
                doc = Document(Utilities.convert_doc_to_docx(Utilities(), doc_path=self.file_path))

            heading_count = self.return_heading_count(doc=doc)
            if heading_count:
                table_data = process_document(file_path)
                return self.chunk_from_heading_based_parser(table_data)
            else:
                parser = TextDocumentParser(self.model, self.tokenizer)
                parsed_data_list = parser.parse(self.file_path, "document", None)
                self.remove_pdf()
                return parsed_data_list

        except Exception as e:
            raise FileParsingException(f"There is an issue while parsing the word file: {str(e)}")

    def chunk_from_heading_based_parser(self, parsed_data: List[Dict]) -> str:
        """
        This function parses the parser format into a single concatenated string
        Args:
            parsed_data: Parser output of WordDocumentParser
        Return:
            Concatenated string of Document Segments
        """
        try:
            concatenated_output = ""
            heading_concatenation = ""
            segment_count = 0
            for dict_element in parsed_data:
                # If the dict segment does not have paragraphs, only heading
                if 'header_content' not in dict_element:
                    heading_concatenation += " " + dict_element.get('header', '')
                else:
                    segment_count += 1
                    heading_concatenation += " " + dict_element.get('header', '')
                    concatenated_output += dict_element.get('header_content', '') + " "
                    # Reset heading concatenation for the next segment
                    heading_concatenation = ""

            # If the document only consisted of headings
            if not concatenated_output and heading_concatenation:
                concatenated_output += heading_concatenation.strip()
            return concatenated_output.strip()

        except Exception as e:
            raise FileParsingException("There is an issue in parsing text based on headings")

    def remove_pdf(self):
        """
        Removes the PDF file corresponding to the current file path if it exists.
        """
        directory, file_with_extension = os.path.split(self.file_path)
        name, extension = os.path.splitext(file_with_extension)
        pdf_path = os.path.join(directory, name + '.pdf')
        if os.path.exists(pdf_path):
            os.remove(pdf_path)