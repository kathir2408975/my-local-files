import torch
from operator import itemgetter
import collections
import pandas as pd
import numpy as np
from functools import reduce
import torch.nn.functional as F
from torch.utils.data import Dataset
from docx import Document
from app.Utilities.WordParserUtilities import Utilities
from collections import defaultdict
from PyPDF2 import PdfReader
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextBoxHorizontal, LTPage
import pdfplumber

from app.exception_handling_layer.exception_handling import FileParsingException


class CustomDataset(Dataset):
    def __init__(self, dataset, tokenizer):
        self.dataset = dataset
        self.tokenizer = tokenizer

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, idx):
        # get item
        example = self.dataset[idx]
        encoding = dict()
        encoding["images_ids"] = example["images_ids"]
        encoding["chunk_ids"] = example["chunk_ids"]
        encoding["input_ids"] = example["input_ids"]
        encoding["attention_mask"] = example["attention_mask"]
        encoding["bbox"] = example["normalized_bboxes"]

        return encoding


class WordDocUtils:
    @staticmethod
    def extract_tables(doc):
        # extract text from the tables
        tables_as_lists = []
        for i, table in enumerate(doc.tables):
            table_row_list = []
            for row in table.rows:
                row_str = ''
                for cell in row.cells:
                    row_str += cell.text + " "
                table_row_list.append(row_str.encode('ascii', "ignore").decode().strip())
            tables_as_lists.append(table_row_list)
        return tables_as_lists


class TextDocumentParser:
    def __init__(self, model, tokenizer) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.word_doc_processor = WordDocUtils()

        # bounding boxes start and end of a sequence
        self.cls_box = [0, 0, 0, 0]
        self.sep_box = self.cls_box
        # (tokenization) The maximum length of a feature (sequence)
        self.max_length = 384
        # (tokenization) overlap
        self.doc_stride = 128  # The authorized overlap between two part of the context when splitting it is needed.

    @staticmethod
    def upperleft_to_lowerright(bbox):
        # converts bboxes to (upper left, lower right) format
        x0, y0, x1, y1 = tuple(bbox)
        if bbox[2] < bbox[0]:
            x0 = bbox[2]
            x1 = bbox[0]
        if bbox[3] < bbox[1]:
            y0 = bbox[3]
            y1 = bbox[1]
        return [x0, y0, x1, y1]

    @staticmethod
    def normalize_box(bbox, width, height):
        return [
            int(1000 * (bbox[0] / width)),
            int(1000 * (bbox[1] / height)),
            int(1000 * (bbox[2] / width)),
            int(1000 * (bbox[3] / height)),
        ]

    @staticmethod
    def denormalize_box(bbox, width, height):
        return [
            width * (bbox[0] / 1000),
            height * (bbox[1] / 1000),
            width * (bbox[2] / 1000),
            height * (bbox[3] / 1000),
        ]

    @staticmethod
    def original_box(box, original_width, original_height, coco_width, coco_height):
        return [
            int(original_width * (box[0] / coco_width)),
            int(original_height * (box[1] / coco_height)),
            int(original_width * (box[2] / coco_width)),
            int(original_height * (box[3] / coco_height)),
        ]


    # function to sort bounding boxes
    @staticmethod
    def get_sorted_boxes(bboxes):
        # sort by y from page top to bottom
        sorted_bboxes = sorted(bboxes, key=itemgetter(1), reverse=False)
        y_list = [bbox[1] for bbox in sorted_bboxes]

        # sort by x from page left to right when boxes with same y
        if len(list(set(y_list))) != len(y_list):
            y_list_duplicates_indexes = dict()
            y_list_duplicates = [item for item, count in collections.Counter(y_list).items() if count > 1]
            for item in y_list_duplicates:
                y_list_duplicates_indexes[item] = [i for i, e in enumerate(y_list) if e == item]
                bbox_list_y_duplicates = sorted(
                    np.array(sorted_bboxes, dtype=object)[y_list_duplicates_indexes[item]].tolist(), key=itemgetter(0),
                    reverse=False)
                np_array_bboxes = np.array(sorted_bboxes)
                np_array_bboxes[y_list_duplicates_indexes[item]] = np.array(bbox_list_y_duplicates)
                sorted_bboxes = np_array_bboxes.tolist()

        return sorted_bboxes

    # sort data from y = 0 to end of page (and after, x=0 to end of page when necessary)
    def sort_data_wo_labels(self, bboxes, texts):

        sorted_bboxes = self.get_sorted_boxes(bboxes)
        sorted_bboxes_indexes = [bboxes.index(bbox) for bbox in sorted_bboxes]
        sorted_texts = np.array(texts, dtype=object)[sorted_bboxes_indexes].tolist()

        return sorted_bboxes, sorted_texts

    @staticmethod
    def extract_text_and_bboxes(pdf_path):
        text_and_bboxes = defaultdict(list)
        for page_num, page_layout in enumerate(extract_pages(pdf_path)):
            if isinstance(page_layout, LTPage):
                page_height = page_layout.height
                for element in page_layout:
                    if isinstance(element, LTTextBoxHorizontal):
                        x0, y0, x1, y1 = element.bbox
                        # Flip y-coordinates and adjust to top-left origin
                        y0_new = page_height - y1
                        y1_new = page_height - y0
                        # Arrange as (x_left, y_top, x_right, y_bottom)
                        bbox = (x0, y0_new, x1, y1_new)
                        text = element.get_text().strip()
                        if text:
                            text_and_bboxes[page_num].append((text, bbox))
        return text_and_bboxes

    @staticmethod
    def convert_pdf_to_images(pdf_path):
        images = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # Get page as an image
                page_image = page.to_image()
                images.append(page_image.original)
        return images

    def extracted_data_from_pdf(self, pdf_path):
        images_ids_list, lines_list, line_boxes_list, images_list, page_no_list, num_pages_list = list(), list(), list(), list(), list(), list()

        try:
            pdf_reader = PdfReader(pdf_path)
            num_pages = len(pdf_reader.pages)

            # Convert PDF pages to images
            pdf_images = self.convert_pdf_to_images(pdf_path)

            text_and_bboxes = self.extract_text_and_bboxes(pdf_path)

            for page_num in range(num_pages):
                page = pdf_reader.pages[page_num]

                # Extract text and bounding boxes
                texts_list = [item[0] for item in text_and_bboxes[page_num]]
                bboxs_list = [list(item[1]) for item in text_and_bboxes[page_num]]

                images_ids_list.append(page_num)
                images_list.append(pdf_images[page_num])
                page_no_list.append(page_num)
                num_pages_list.append(num_pages)
                lines_list.append(texts_list)
                line_boxes_list.append(bboxs_list)

        except Exception as e:
            raise FileParsingException("There's error in extracting data from the pdf")
        else:
            from datasets import Dataset
            dataset = Dataset.from_dict({
                "images_ids": images_ids_list,
                "images": images_list,
                "page_no": page_no_list,
                "num_pages": num_pages_list,
                "texts": lines_list,
                "bboxes_line": line_boxes_list
            })

            return dataset

    def prepare_inference_features(self, example, cls_box: list = None, sep_box: list = None):
        if not cls_box:
            cls_box = self.cls_box
            sep_box = self.sep_box

        images_ids_list, chunks_ids_list, input_ids_list, attention_mask_list, bb_list = list(), list(), list(), list(), list()

        # get batch
        batch_images_ids = example["images_ids"]
        batch_images = example["images"]
        batch_bboxes_line = example["bboxes_line"]
        batch_texts = example["texts"]
        batch_images_size = [image.size for image in batch_images]

        batch_width, batch_height = [image_size[0] for image_size in batch_images_size], [image_size[1] for image_size
                                                                                          in batch_images_size]

        # add a dimension if not a batch but only one image
        if not isinstance(batch_images_ids, list):
            batch_images_ids = [batch_images_ids]
            batch_images = [batch_images]
            batch_bboxes_line = [batch_bboxes_line]
            batch_texts = [batch_texts]
            batch_width, batch_height = [batch_width], [batch_height]

        # process all images of the batch
        for num_batch, (image_id, boxes, texts, width, height) in enumerate(
                zip(batch_images_ids, batch_bboxes_line, batch_texts, batch_width, batch_height)):
            tokens_list = []
            bboxes_list = []

            # add a dimension if only one image
            if not isinstance(texts, list):
                texts, boxes = [texts], [boxes]

            # convert boxes to original
            normalize_bboxes_line = [self.normalize_box(self.upperleft_to_lowerright(box), width, height) for box in
                                     boxes]

            # sort boxes with texts
            # we want sorted lists from top to bottom of the image
            boxes, texts = self.sort_data_wo_labels(normalize_bboxes_line, texts)

            for box, text in zip(boxes, texts):
                tokens = self.tokenizer.tokenize(text)
                num_tokens = len(tokens)  # get number of tokens
                tokens_list.extend(tokens)
                bboxes_list.extend([box] * num_tokens)  # number of boxes must be the same as the number of tokens

            # use of return_overflowing_tokens=True / stride=doc_stride
            # to get parts of image with overlap
            # source: https://huggingface.co/course/chapter6/3b?fw=tf#handling-long-contexts
            encodings = self.tokenizer(" ".join(texts),
                                       truncation=True,
                                       padding="max_length",
                                       max_length=self.max_length,
                                       stride=self.doc_stride,
                                       return_overflowing_tokens=True,
                                       return_offsets_mapping=True
                                       )

            encodings.pop("overflow_to_sample_mapping")
            offset_mapping = encodings.pop("offset_mapping")

            # labeling examples to get their boxes
            sequence_length_prev = 0
            for i, offsets in enumerate(offset_mapping):
                # truncate tokens, boxes and labels based on length of chunk - 2 (special tokens <s> and </s>)
                sequence_length = len(encodings.input_ids[i]) - 2
                if i == 0:
                    start = 0
                else:
                    start += sequence_length_prev - self.doc_stride
                end = start + sequence_length
                sequence_length_prev = sequence_length

                # get tokens, boxes and labels of this image chunk
                bb = [cls_box] + bboxes_list[start:end] + [sep_box]

                # as the last chunk can have a length < max_length
                # we must add [tokenizer.pad_token] (tokens), [sep_box] (boxes) and [-100] (labels)
                if len(bb) < self.max_length:
                    bb = bb + [sep_box] * (self.max_length - len(bb))

                # append results
                input_ids_list.append(encodings["input_ids"][i])
                attention_mask_list.append(encodings["attention_mask"][i])
                bb_list.append(bb)
                images_ids_list.append(image_id)
                chunks_ids_list.append(i)

        return {
            "images_ids": images_ids_list,
            "chunk_ids": chunks_ids_list,
            "input_ids": input_ids_list,
            "attention_mask": attention_mask_list,
            "normalized_bboxes": bb_list,
        }

    # get predictions at token level
    # since segments of document can be longer than input length we get predictions on tokens and then combine them to
    # get prediction for the line
    def predictions_token_level(self, images, custom_encoded_dataset):

        num_imgs = len(images)
        if num_imgs > 0:

            chunk_ids, input_ids, bboxes, outputs, token_predictions = dict(), dict(), dict(), dict(), dict()
            images_ids_list = list()
            # dataloader = DataLoader(custom_encoded_dataset, batch_size=32, shuffle=True)
            for i, encoding in enumerate(custom_encoded_dataset):

                # get custom encoded data
                image_id = encoding['images_ids']
                chunk_id = encoding['chunk_ids']
                input_id = torch.tensor(encoding['input_ids'])[None]
                attention_mask = torch.tensor(encoding['attention_mask'])[None]
                bbox = torch.tensor(encoding['bbox'])[None]

                # save data in dictionaries
                if image_id not in images_ids_list:
                    images_ids_list.append(image_id)

                if image_id in chunk_ids:
                    chunk_ids[image_id].append(chunk_id)
                else:
                    chunk_ids[image_id] = [chunk_id]

                if image_id in input_ids:
                    input_ids[image_id].append(input_id)
                else:
                    input_ids[image_id] = [input_id]

                if image_id in bboxes:
                    bboxes[image_id].append(bbox)
                else:
                    bboxes[image_id] = [bbox]

                # get prediction
                with torch.no_grad():
                    output = self.model(
                        input_ids=input_id,
                        attention_mask=attention_mask,
                        bbox=bbox
                    )

                # save probabilities of predictions in dictionary
                if image_id in outputs:
                    outputs[image_id].append(F.softmax(output.logits.squeeze(), dim=-1))
                else:
                    outputs[image_id] = [F.softmax(output.logits.squeeze(), dim=-1)]

            return outputs, images_ids_list, chunk_ids, input_ids, bboxes

    # Get predictions (line level)
    def predictions_line_level(self, outputs, images_list, images_ids_list, chunk_ids, input_ids, bboxes):

        bboxes_list_dict, input_ids_dict_dict, probs_dict_dict, df = dict(), dict(), dict(), dict()

        if len(images_ids_list) > 0:

            for i, image_id in enumerate(images_ids_list):

                # get image information
                # images_list = dataset.filter(lambda example: example["images_ids"] == image_id)["images"]
                image = images_list[0]
                width, height = image.size

                # get data
                outputs_list = outputs[image_id]
                input_ids_list = input_ids[image_id]
                bboxes_list = bboxes[image_id]

                # create zeros tensors
                # each line is divided in multiple tokens with an output prediction of dimensions m*n,
                # so we will create a tensor of dimensions (m*len(number of outputs)) * n
                ten_probs = torch.zeros((outputs_list[0].shape[0] - 2) * len(outputs_list), outputs_list[0].shape[1])
                ten_input_ids = torch.ones(size=(1, (outputs_list[0].shape[0] - 2) * len(outputs_list)), dtype=int)
                ten_bboxes = torch.zeros(size=(1, (outputs_list[0].shape[0] - 2) * len(outputs_list), 4), dtype=int)

                if len(outputs_list) > 1:

                    for num_output, (output, input_id, bbox) in enumerate(
                            zip(outputs_list, input_ids_list, bboxes_list)):
                        start = num_output * (self.max_length - 2) - max(0, num_output) * self.doc_stride
                        end = start + (self.max_length - 2)

                        if num_output == 0:
                            ten_probs[start:end, :] += output[1:-1]
                            ten_input_ids[:, start:end] = input_id[:, 1:-1]
                            ten_bboxes[:, start:end, :] = bbox[:, 1:-1, :]
                        else:
                            ten_probs[start:start + self.doc_stride, :] += output[1:1 + self.doc_stride]
                            ten_probs[start:start + self.doc_stride, :] = ten_probs[start:start + self.doc_stride,
                                                                          :] * 0.5
                            ten_probs[start + self.doc_stride:end, :] += output[1 + self.doc_stride:-1]

                            ten_input_ids[:, start:start + self.doc_stride] = input_id[:, 1:1 + self.doc_stride]
                            ten_input_ids[:, start + self.doc_stride:end] = input_id[:, 1 + self.doc_stride:-1]

                            ten_bboxes[:, start:start + self.doc_stride, :] = bbox[:, 1:1 + self.doc_stride, :]
                            ten_bboxes[:, start + self.doc_stride:end, :] = bbox[:, 1 + self.doc_stride:-1, :]

                else:
                    ten_probs += outputs_list[0][1:-1]
                    ten_input_ids = input_ids_list[0][:, 1:-1]
                    ten_bboxes = bboxes_list[0][:, 1:-1]

                ten_probs_list, ten_input_ids_list, ten_bboxes_list = ten_probs.tolist(), ten_input_ids.tolist()[0], \
                    ten_bboxes.tolist()[0]
                bboxes_list = list()
                input_ids_dict, probs_dict = dict(), dict()
                bbox_prev = [-100, -100, -100, -100]
                for probs, input_id, bbox in zip(ten_probs_list, ten_input_ids_list, ten_bboxes_list):
                    bbox = self.denormalize_box(bbox, width, height)
                    if bbox != bbox_prev and bbox != self.cls_box and bbox != self.sep_box and bbox[0] != bbox[2] and \
                            bbox[1] != \
                            bbox[3]:
                        bboxes_list.append(bbox)
                        input_ids_dict[str(bbox)] = [input_id]
                        probs_dict[str(bbox)] = [probs]
                    elif bbox != self.cls_box and bbox != self.sep_box and bbox[0] != bbox[2] and bbox[1] != bbox[3]:
                        input_ids_dict[str(bbox)].append(input_id)
                        probs_dict[str(bbox)].append(probs)
                    bbox_prev = bbox

                probs_bbox = dict()
                for i, bbox in enumerate(bboxes_list):
                    probs = probs_dict[str(bbox)]
                    probs = np.array(probs).T.tolist()

                    probs_label = list()
                    for probs_list in probs:
                        prob_label = reduce(lambda x, y: x * y, probs_list)
                        prob_label = prob_label ** (1. / (len(probs_list)))  # normalization
                        probs_label.append(prob_label)
                    max_value = max(probs_label)
                    max_index = probs_label.index(max_value)
                    probs_bbox[str(bbox)] = max_index

                bboxes_list_dict[image_id] = bboxes_list
                input_ids_dict_dict[image_id] = input_ids_dict
                probs_dict_dict[image_id] = probs_bbox

                df[image_id] = pd.DataFrame()
                df[image_id]["bboxes"] = bboxes_list
                df[image_id]["texts"] = [self.tokenizer.decode(input_ids_dict[str(bbox)]) for bbox in bboxes_list]
                df[image_id]["labels"] = [self.model.config.id2label[probs_bbox[str(bbox)]] for bbox in bboxes_list]

            return probs_bbox, bboxes_list_dict, input_ids_dict_dict, probs_dict_dict, df

        else:
            print("An error occurred while getting predictions!")

    def pdf_processor(self, pdf_path):
        dataset = self.extracted_data_from_pdf(pdf_path)
        encoded_dataset = dataset.map(self.prepare_inference_features, batched=True, batch_size=64,
                                      remove_columns=dataset.column_names)
        custom_encoded_dataset = CustomDataset(encoded_dataset, self.tokenizer)

        images_list = [i['images'] for i in dataset]

        # Get predictions (token level)
        outputs, images_ids_list, chunk_ids, input_ids, bboxes = self.predictions_token_level(images_list,
                                                                                              custom_encoded_dataset)
        # Get predictions (line level)
        # function returns probs_bbox, bboxes_list_dict, input_ids_dict_dict, probs_dict_dict, df
        _, _, _, _, df = self.predictions_line_level(outputs, images_list, images_ids_list, chunk_ids, input_ids,
                                                     bboxes)
        return df

    def combine_datasets(self, df_list):
        # If df_list is a dict, convert its values into a list of dataframes.
        dfs = []
        for i, df in enumerate(df_list.values(), 1):
            df = df.copy()
            df['page_no'] = i
            dfs.append(df)
        merged_df = pd.concat(dfs, ignore_index=True)
        return merged_df

    def _table_cleaner(self, doc_parsed_df, tables_as_lists, table_start_text, table_end_text):
        # doc_parsed_df is a DataFrame with columns 'texts' and 'labels'

        # Function to check if a row corresponds to a table
        def is_table_start(row, table_start_text):
            return table_start_text in row['texts']

        def is_table_end(row, table_end_text):
            return table_end_text in row['texts']

        # Find the index of the start and end rows of the table in the DataFrame
        start_rows = doc_parsed_df[doc_parsed_df.apply(lambda row: is_table_start(row, table_start_text), axis=1)]
        end_rows = doc_parsed_df[doc_parsed_df.apply(lambda row: is_table_end(row, table_end_text), axis=1)]

        # Check if start and end rows are found
        if not start_rows.empty and not end_rows.empty:
            start_row = start_rows.iloc[0]
            end_row = end_rows.iloc[0]
            # Find the start and end positions within the row's text

            start_position = start_row['texts'].find(table_start_text)
            end_position = end_row['texts'].find(table_end_text[-15:]) + len(table_end_text[-15:])

            # Extract the relevant portion from the document text
            # document_text = ' '.join(doc_parsed_df['texts'])
            # table_combined_text = document_text[start_row.name + start_position:end_row.name + end_position]

            # Replace the text related to the table with an empty string in the DataFrame
            start_text = start_row['texts'][:start_position] + start_row['texts'][start_position:].replace(
                table_start_text, '')
            start_page = start_row['page_no']
            doc_parsed_df.at[start_row.name, 'texts'] = start_text
            end_text = end_row['texts'][end_position:].replace(table_end_text, '')
            doc_parsed_df.at[end_row.name, 'texts'] = end_text
            drop_start = start_row.name + 1 if len(start_text.strip()) else start_row.name
            drop_end = end_row.name if len(end_text.strip()) else end_row.name + 1
            doc_parsed_df = doc_parsed_df.drop(doc_parsed_df.index[drop_start:drop_end])

            # Add individual rows of the table to the DataFrame
            table_rows = tables_as_lists
            for i, row_text in enumerate(table_rows):
                if row_text.strip():
                    if i == 0:
                        table_row = pd.DataFrame({'texts': row_text, 'labels': 'table_head', 'page_no': start_page},
                                                 index=[0])
                    else:
                        table_row = pd.DataFrame({'texts': row_text, 'labels': 'table_row', 'page_no': start_page},
                                                 index=[0])
                    doc_parsed_df = pd.concat([doc_parsed_df, table_row], ignore_index=True)
        # Now, doc_parsed_df contains the original text with table rows combined into a single string
        # first row of tables are added as table label
        # and individual rows added as 'table_row' label
        return doc_parsed_df

    def _join_by_label(self, df):
        result_rows = []

        # Iterate through the DataFrame
        current_label = None
        current_text = ""
        current_page_no = None

        for index, row in df.iterrows():
            if current_label is None:
                current_label = row['labels']
                current_text = row['texts']
                current_page_no = row['page_no']
            elif row['labels'] == current_label or row['labels'] == "Page-footer":
                current_text += " " + row['texts']
            else:
                result_rows.append({'labels': current_label, 'texts': current_text, 'page_no': current_page_no})
                current_label = row['labels']
                current_text = row['texts']
                current_page_no = row['page_no']

        # Add the last group to the result
        result_rows.append({'labels': current_label, 'texts': current_text, 'page_no': current_page_no})

        # Create a new DataFrame from the result list
        result_df = pd.DataFrame(result_rows)

        # Display the result DataFrame
        return result_df

    def df_to_parser_format(self, df, document_path: str) -> str:
        """
        This function converts a DataFrame into a single concatenated string format.
        :param df: DataFrame containing the parsed document data
        :param document_path: Path to the document (not used in this function)
        :return: Concatenated string of document segments
        """
        concatenated_output = ""

        for index, row in df.iterrows():
            if row["labels"] in ["Section-header", "table-head"] or not concatenated_output:
                # Start a new segment
                concatenated_output += row["texts"] + " "
            else:
                # Append to the last segment
                concatenated_output += row["texts"] + " "

        return concatenated_output.strip()  # Return the final concatenated string

    def parse(self, document_path, file_type, image_handler=None) -> str:
        utilities = Utilities()
        if file_type == "document":
            pdfpath = utilities.docx_to_pdf(document_path)
        else:
            pdfpath = document_path
        if pdfpath:
            model_parsed_df_list = self.pdf_processor(pdfpath)
            model_parsed_df = self.combine_datasets(model_parsed_df_list)
            if file_type == "document":
                if document_path[-3:] == "doc":
                    document_path += "x"
                doc = Document(document_path)
                tables_as_lists = self.word_doc_processor.extract_tables(doc)
                for table in tables_as_lists:
                    model_parsed_df = self._table_cleaner(model_parsed_df, table, table[0], table[-1])

            model_parsed_df = self._join_by_label(model_parsed_df)

            # convert dataframe to graph creation chunked format
            parser_format_data = self.df_to_parser_format(model_parsed_df,document_path)

            return parser_format_data
