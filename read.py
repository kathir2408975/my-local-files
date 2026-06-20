import os
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import docx2txt
from docx2pdf import convert

# Change this to your poppler bin folder path
POPPLER_PATH = r"C:\Users\UTHRAVFST\AppData\Roaming\Microsoft\Windows\Network Shortcuts\Release-24.08.0-0\poppler-24.08.0\Library\bin"

input_folder = r"all_file_1"

def extract_from_pdf(pdf_path, file_name):
    doc = fitz.open(pdf_path)

    # Create folder for this PDF
    output_path = os.path.join(input_folder, "extracted_output_1", file_name)
    os.makedirs(output_path, exist_ok=True)

    full_text = ""

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text().strip()

        if len(text) > 20:
            full_text += f"\n--- Page {page_num + 1} ---\n{text}\n"

            images = page.get_images(full=True)
            for img_index, img in enumerate(images, start=1):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                image_filename = f"{file_name}_page{page_num + 1}_img{img_index}.{image_ext}"
                with open(os.path.join(output_path, image_filename), "wb") as img_file:
                    img_file.write(image_bytes)
        else:
            # Convert full page to image if text is minimal
            images = convert_from_path(pdf_path, first_page=page_num+1, last_page=page_num+1, poppler_path=POPPLER_PATH)
            for i, img in enumerate(images):
                image_filename = f"{file_name}_page{page_num + 1}_converted.png"
                img.save(os.path.join(output_path, image_filename), "PNG")


    doc.close()

    # Save all collected text in one file
    text_file_path = os.path.join(output_path, f"{file_name}.txt")
    with open(text_file_path, "w", encoding="utf-8") as f:
        f.write(full_text)

def extract_from_docx(docx_path, file_name):
    output_path = os.path.join(input_folder, "extracted_output_1", file_name)
    os.makedirs(output_path, exist_ok=True)

    # Extract text and images
    text = docx2txt.process(docx_path, output_path)

    full_text = ""
    if len(text.strip()) > 20:
        full_text += f"\n--- Page 1 ---\n{text}\n"
    else:
        # Text is very short => possibly scanned docx (mostly images)
        # Convert docx to PDF for further processing if needed
        pdf_output_path = os.path.join(output_path, f"{file_name}.pdf")
        try:
            convert(docx_path, pdf_output_path)
            print(f"Converted scanned docx to PDF: {pdf_output_path}")
        except Exception as e:
            print(f"Error converting docx to PDF: {e}")

    # Save text file if any text extracted
    if full_text:
        text_filename = f"{file_name}.txt"
        with open(os.path.join(output_path, text_filename), "w", encoding="utf-8") as f:
            f.write(full_text)

    # Rename images extracted by docx2txt
    img_counter = 1
    for img_file in os.listdir(output_path):
        if img_file.lower().startswith("image") and img_file.lower().endswith((".png", ".jpg", ".jpeg")):
            old_path = os.path.join(output_path, img_file)
            ext = os.path.splitext(img_file)[1]
            new_name = f"{file_name}_page{img_counter}{ext}"
            new_path = os.path.join(output_path, new_name)
            os.rename(old_path, new_path)
            img_counter += 1


for file in os.listdir(input_folder):
    file_path = os.path.join(input_folder, file)
    file_name, ext = os.path.splitext(file)
    ext = ext.lower()

    if os.path.isfile(file_path):
        if ext == ".pdf":
            extract_from_pdf(file_path, file_name)
        elif ext == ".docx":
            extract_from_docx(file_path, file_name)

print("✅ All data extracted and saved page-wise.")



# import docx2txt
# import os

# def extract_with_images(docx_path, output_folder):
#     # Create output folder if it doesn't exist
#     os.makedirs(output_folder, exist_ok=True)
    
#     # Extract text and images
#     text = docx2txt.process(docx_path, output_folder)
    
#     # Check what images were extracted
#     image_files = []
#     if os.path.exists(output_folder):
#         for file in os.listdir(output_folder):
#             if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
#                 image_files.append(file)
    
#     # Find image placeholders in text
#     image_positions = []
#     lines = text.split('\n')
#     for i, line in enumerate(lines):
#         if '[image:' in line.lower() or any(img_file in line for img_file in image_files):
#             image_positions.append(i)
    
#     return text, image_files, image_positions

# # Usage
# text, images, positions = extract_with_images('P1176350810d2207085720b8375844f085.docx', 'extracted_images/')
# print(f"Found {len(images)} images")
# print(f"Image positions in text: {positions}")






#### rachit code


# import os
# import torch
# import collections
# import numpy as np
# import pandas as pd
# from PyPDF2 import PdfReader
# from functools import reduce
# from operator import itemgetter
# import torch.nn.functional as F
# import pdfplumber
# from pdfminer.high_level import extract_pages
# from pdfminer.layout import LTTextBoxHorizontal, LTPage
# from transformers import AutoTokenizer, AutoModelForTokenClassification
# from datasets import Dataset
# from torch.utils.data import Dataset as TorchDataset

# # ----------- Custom Dataset for Model ------------
# class CustomDataset(TorchDataset):
#     def __init__(self, dataset, tokenizer):
#         self.dataset = dataset
#         self.tokenizer = tokenizer

#     def __len__(self):
#         return len(self.dataset)

#     def __getitem__(self, idx):
#         example = self.dataset[idx]
#         encoding = {
#             "images_ids": example["images_ids"],
#             "chunk_ids": example["chunk_ids"],
#             "input_ids": example["input_ids"],
#             "attention_mask": example["attention_mask"],
#             "bbox": example["normalized_bboxes"]
#         }
#         return encoding

# # ----------- TextDocumentParser ------------
# class TextDocumentParser:
#     def __init__(self, model, tokenizer):
#         self.model = model
#         self.tokenizer = tokenizer
#         self.max_length = 384
#         self.doc_stride = 128
#         self.cls_box = [0, 0, 0, 0]
#         self.sep_box = self.cls_box

#     @staticmethod
#     def extract_text_and_bboxes(pdf_path):
#         text_and_bboxes = collections.defaultdict(list)
#         for page_num, layout in enumerate(extract_pages(pdf_path)):
#             if isinstance(layout, LTPage):
#                 page_height = layout.height
#                 for element in layout:
#                     if isinstance(element, LTTextBoxHorizontal):
#                         x0, y0, x1, y1 = element.bbox
#                         y0, y1 = page_height - y1, page_height - y0
#                         bbox = (x0, y0, x1, y1)
#                         text = element.get_text().strip()
#                         if text:
#                             text_and_bboxes[page_num].append((text, bbox))
#         return text_and_bboxes

#     @staticmethod
#     def convert_pdf_to_images(pdf_path):
#         images = []
#         with pdfplumber.open(pdf_path) as pdf:
#             for page in pdf.pages:
#                 images.append(page.to_image().original)
#         return images

#     @staticmethod
#     def normalize_box(bbox, width, height):
#         return [
#             int(1000 * (bbox[0] / width)),
#             int(1000 * (bbox[1] / height)),
#             int(1000 * (bbox[2] / width)),
#             int(1000 * (bbox[3] / height)),
#         ]

#     def sort_data_wo_labels(self, bboxes, texts):
#         sorted_bboxes = sorted(bboxes, key=itemgetter(1))
#         indexes = [bboxes.index(bbox) for bbox in sorted_bboxes]
#         return sorted_bboxes, [texts[i] for i in indexes]

#     def prepare_inference_features(self, example):
#         inputs = {
#             "images_ids": [],
#             "chunk_ids": [],
#             "input_ids": [],
#             "attention_mask": [],
#             "normalized_bboxes": [],
#         }

#         for i, (image, image_id, boxes, texts) in enumerate(zip(
#             example["images"], example["images_ids"], example["bboxes_line"], example["texts"]
#         )):
#             width, height = image.size
#             tokens, bboxes = [], []

#             boxes = [self.normalize_box(b, width, height) for b in boxes]
#             boxes, texts = self.sort_data_wo_labels(boxes, texts)

#             for box, text in zip(boxes, texts):
#                 tokenized = self.tokenizer.tokenize(text)
#                 tokens.extend(tokenized)
#                 bboxes.extend([box] * len(tokenized))

#             encoding = self.tokenizer(
#                 " ".join(texts),
#                 truncation=True,
#                 padding="max_length",
#                 max_length=self.max_length,
#                 stride=self.doc_stride,
#                 return_overflowing_tokens=True,
#                 return_offsets_mapping=True
#             )

#             encoding.pop("overflow_to_sample_mapping")
#             for i, _ in enumerate(encoding["offset_mapping"]):
#                 bb = [self.cls_box] + bboxes[:self.max_length - 2] + [self.sep_box]
#                 bb += [self.sep_box] * (self.max_length - len(bb))
#                 inputs["images_ids"].append(image_id)
#                 inputs["chunk_ids"].append(i)
#                 inputs["input_ids"].append(encoding["input_ids"][i])
#                 inputs["attention_mask"].append(encoding["attention_mask"][i])
#                 inputs["normalized_bboxes"].append(bb)

#         return inputs

#     def extracted_data_from_pdf(self, pdf_path):
#         reader = PdfReader(pdf_path)
#         num_pages = len(reader.pages)
#         pdf_images = self.convert_pdf_to_images(pdf_path)
#         text_and_bboxes = self.extract_text_and_bboxes(pdf_path)

#         dataset_dict = {
#             "images_ids": [],
#             "images": [],
#             "page_no": [],
#             "num_pages": [],
#             "texts": [],
#             "bboxes_line": [],
#         }

#         for page_num in range(num_pages):
#             texts = [item[0] for item in text_and_bboxes[page_num]]
#             bboxes = [list(item[1]) for item in text_and_bboxes[page_num]]
#             dataset_dict["images_ids"].append(page_num)
#             dataset_dict["images"].append(pdf_images[page_num])
#             dataset_dict["page_no"].append(page_num)
#             dataset_dict["num_pages"].append(num_pages)
#             dataset_dict["texts"].append(texts)
#             dataset_dict["bboxes_line"].append(bboxes)

#         return Dataset.from_dict(dataset_dict)

#     def df_to_parser_format(self, df):
#         return " ".join(df["texts"].tolist()).strip()

#     def pdf_to_text(self, pdf_path):
#         dataset = self.extracted_data_from_pdf(pdf_path)
#         encoded_dataset = dataset.map(
#             self.prepare_inference_features,
#             batched=True,
#             batch_size=64,
#             remove_columns=dataset.column_names,
#         )
#         custom_dataset = CustomDataset(encoded_dataset, self.tokenizer)
#         images = [i['images'] for i in dataset]

#         outputs = {}
#         for i, data in enumerate(custom_dataset):
#             input_id = torch.tensor(data["input_ids"])[None]
#             attention_mask = torch.tensor(data["attention_mask"])[None]
#             bbox = torch.tensor(data["bbox"])[None]

#             with torch.no_grad():
#                 output = self.model(input_ids=input_id, attention_mask=attention_mask, bbox=bbox)

#             probs = F.softmax(output.logits.squeeze(), dim=-1)
#             decoded = self.tokenizer.decode([x for x in data["input_ids"] if x not in [0, 101, 102]])
#             outputs[i] = decoded

#         all_text = "\n".join(outputs.values())
#         return all_text

# # ----------- RUN SCRIPT ------------
# if __name__ == "__main__":
#     pdf_path = "tableData_Program Appraisal Document.pdf"  # Replace with your file
#     model_id = "pierreguillou/lilt-xlm-roberta-base-finetuned-with-DocLayNet-base-at-linelevel-ml384"
#     tokenizer = AutoTokenizer.from_pretrained(model_id)
#     model = AutoModelForTokenClassification.from_pretrained(model_id)

#     parser = TextDocumentParser(model, tokenizer)
#     text_output = parser.pdf_to_text(pdf_path)

#     print("\n📄 Extracted Document Text:\n")
#     print(text_output)

#     with open("huggingface_onepage_pdf.txt", "w", encoding="utf-8") as f:
#         f.write(text_output)
