from configs.bank_configs import bank_parsing_spec
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage

# From PDFInterpreter import both PDFResourceManager and PDFPageInterpreter

from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter

# Import this to raise exception whenever text extraction from PDF is not allowed
from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTChar
from pdfminer.converter import PDFPageAggregator

from collections import defaultdict


class BankDetector:

    def __init__(self):
        self.extracted_text = []
        self.bank = ''
        self.flag = 0
        self.page_num = 1
        self.char_id = 0

    def fetch_chars(self, lt_obj):
        if isinstance(lt_obj, LTChar):
            self.extracted_text.append({
                'bbox': lt_obj.bbox,
                'page_num': self.page_num,
                'text': lt_obj.get_text()
            })
        if not hasattr(lt_obj, '_objs'):
            return
        objs = lt_obj._objs
        if not objs:
            return
        for obj in objs:
            self.fetch_chars(obj)

    def character_extraction(self, address):
        # Create a file pointer
        fp = open(address, 'rb')

        try:
            # Create parser object to parse the pdf content
            parser = PDFParser(fp)

            # Store the parsed content in PDFDocument object
            document = PDFDocument(parser, '')

            # Create PDFResourceManager object that stores shared resources such as fonts or images
            rsrcmgr = PDFResourceManager()

            # set parameters for analysis
            laparams = LAParams()

            # Create a PDFDevice object which translates interpreted information into desired format
            # Device needs to be connected to resource manager to store shared resources
            # device = PDFDevice(rsrcmgr)
            # Extract the decive to page aggregator to get LT object elements
            device = PDFPageAggregator(rsrcmgr, laparams=laparams)

            # Create interpreter object to process page content from PDFDocument
            # Interpreter needs to be connected to resource manager for shared resources and device
            interpreter = PDFPageInterpreter(rsrcmgr, device)
            for page in PDFPage.create_pages(document):
                # As the interpreter processes the page stored in PDFDocument object
                interpreter.process_page(page)
                # The device renders the layout from interpreter
                layout = device.get_result()
                # Out of the many LT objects within layout, we are interested in LTTextBox and LTTextLine
                for lt_obj in layout:
                    if isinstance(lt_obj, (LTTextBox, LTTextLine)):
                        self.fetch_chars(lt_obj)
        finally:
            fp.close()

    def remap_characters(self):
        mapper = defaultdict(lambda: defaultdict(list))

        for char_text in self.extracted_text:
            mapper[char_text['page_num']][char_text['bbox'][1]].append(char_text)

        return mapper

    def get_bank_type(self, address):
        self.character_extraction(address)

        # Since, we always read form left to right, optimize data to be read from left to right.
        # This would help us find the location of different headers. It is also required to find co-ordinates
        remapped = self.remap_characters()
        for page_num in range(1, len(remapped) + 1):
            data_set = []

            for key, val in remapped[page_num].items():
                data_set.append((key, val))

            data_set = sorted(data_set, key=lambda x: -x[0])

            self.sort_rows(data_set)

    def sort_rows(self, data_set):
        if self.flag == 1:
            return
        else:
            for row in data_set:
                row_sorted = sorted(row[1], key=lambda x: x['bbox'][0])
                self.construct_string(row_sorted)

    def construct_string(self, row_sorted):
        if self.flag == 1:
            return
        else:
            line_string = ''
            prev = row_sorted[0]['bbox'][0]
            for entry in row_sorted:
                if abs(prev - entry['bbox'][0]) < 1e-3:
                    line_string += entry['text']
                else:
                    line_string += ' ' + entry['text']
                prev = entry['bbox'][2]
            if self.bank == '':
                self.check_bank(line_string)

    def check_bank(self, line):
        if self.flag == 1:
            return
        else:
            try:
                for key, val in bank_parsing_spec.items():
                    if 'page_conf' in val:
                        if line == val['page_conf'][1]['start_row']:
                            self.bank = key
                            self.flag = 1
                            break
            except Exception as e:
                print('Error {}'.format(e))


if __name__ == '__main__':
    parser_obj = BankDetector()
    parser_obj.get_bank_type('hdfc_old.pdf')
    print(parser_obj.bank)

