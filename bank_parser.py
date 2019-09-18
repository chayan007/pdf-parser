from configs.bank_configs import bank_parsing_spec
from bank_format import BankDetector
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage

# From PDFInterpreter import both PDFResourceManager and PDFPageInterpreter

from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter

# Import this to raise exception whenever text extraction from PDF is not allowed
from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTChar
from pdfminer.converter import PDFPageAggregator

from collections import defaultdict
import datetime
import arrow


class Parser(BankDetector):

    def __init__(self, bank_detector):
        super().__init__()
        self.char_id = 0  # Unique id to every extracted character
        self.extracted_text = []  # Extracting every character
        self.page_num = 1  # For parsing page by page
        self.txn_string = ''  # To store the narration (in case of multi-line)
        self.start_marker = ''
        self.end_marker = ''
        self.overall_end_marker = ''
        self.total_characters = 0
        self.current_transaction = {}
        self.bank = ''
        self.curr_date = ''
        self.transactions = []

    def increment_char_id(self, random):
        self.char_id = random + 1

    def fetch_chars(self, lt_obj):
        if isinstance(lt_obj, LTChar):
            self.extracted_text.append({
                'bbox': lt_obj.bbox,
                'page_num': self.page_num,
                'text': lt_obj.get_text(),
                'char_id': self.char_id
            })
            self.increment_char_id(self.char_id)
        if not hasattr(lt_obj, '_objs'):
            return
        objs = lt_obj._objs
        if not objs:
            return
        for obj in objs:
            self.fetch_chars(obj)

    @staticmethod
    def parse_float(input_str):
        if not input_str:
            return 0
        input_str = input_str.replace(',', '')
        return float(input_str)

    @staticmethod
    def does_range_overlap(range_1, range_2):
        if range_1[1] < range_2[0]:
            return False
        if range_1[0] > range_2[1]:
            return False
        return True

    def find_texts_in_row(self, page_num, word_range):
        overlapping_texts = []
        for text in self.extracted_text:
            if text['page_num'] != page_num:
                continue
            if self.does_range_overlap(word_range, (text['bbox'][1], text['bbox'][3])):
                overlapping_texts.append(text)
        return overlapping_texts

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
                self.page_num += 1
        finally:
            fp.close()

    def remap_characters(self):
        mapper = defaultdict(lambda: defaultdict(list))

        for char_text in self.extracted_text:
            mapper[char_text['page_num']][char_text['bbox'][1]].append(char_text)

        return mapper

    def construct_string(self, row_sorted):
        line_string = ''
        prev = row_sorted[0]['bbox'][0]
        for entry in row_sorted:
            if abs(prev - entry['bbox'][0]) < 1e-3:
                line_string += entry['text']
            else:
                line_string += ' ' + entry['text']
            prev = entry['bbox'][2]
        return line_string

    def parse_records(self):
        for key, val in self.current_transaction.items():
            if isinstance(val, list):
                if len(val) == 0:
                    self.current_transaction[key] = ''
                    continue

                part = ''

                prev = val[0]['bbox'][0]

                for entry in val:
                    if entry['bbox'][1] == val[0]['bbox'][1]:
                        if abs(prev - entry['bbox'][0]) < 1e-3:
                            part += entry['text']
                        else:
                            part += ' ' + entry['text']
                        prev = entry['bbox'][2]
                    else:
                        continue

                self.current_transaction[key] = part

    def create_transaction(self, constructed_string):
        if len(constructed_string) != bank_parsing_spec[self.bank]['date_format']['length']:
            try:
                self.curr_date = datetime.datetime.strptime(
                    constructed_string[:bank_parsing_spec[self.bank]['date_format']['length']],
                    bank_parsing_spec[self.bank]['date_format']['date_string']
                )
                # if bank_parsing_spec[self.bank]['error_flag']:
                self.declare_current_transaction()
            except:
                self.txn_string += constructed_string

    def row_to_records(self, row_sorted):
        try:
            for entry in row_sorted:
                for key, val in bank_parsing_spec[self.bank]['cols_conf'].items():
                    if val[0] <= entry['bbox'][0] <= val[1]:
                        self.current_transaction[key].append(entry)
        except:
            return

    def parse_rows(self, data_set):
        has_started = False
        self.current_transaction = {
            'txn_date': '',
            'txn_msg': '',
            'debit_amount': '',
            'credit_amount': '',
            'running_balance': ''
        }
        for row in data_set:
            row_sorted = sorted(row[1], key=lambda x: x['bbox'][0])
            constructed_string = self.construct_string(row_sorted)
            if constructed_string.find(self.end_marker) != -1:
                break

            if constructed_string == self.overall_end_marker:
                self.transactions.append(self.parse_records())
                break

            if has_started:
                if bank_parsing_spec[self.bank]['error_flag']:
                    self.lattice_records(
                        constructed_string,
                        row_sorted
                    )
                else:
                    self.stream_records(
                        constructed_string,
                        row_sorted
                    )

            if constructed_string.find(self.start_marker) >= 0:
                has_started = True

    def stream_records(self, constructed_string, row_sorted):
        self.create_transaction(constructed_string)
        try:
            for entry in row_sorted:
                for key, val in bank_parsing_spec[self.bank]['cols_conf'].items():
                    if val[0] <= entry['bbox'][0] <= val[1]:
                        self.current_transaction[key].append(entry)
        except:
            return
        if self.current_transaction['running_balance']:
            self.parse_records()
            self.transactions.append(self.current_transaction)
        if self.txn_string and self.current_transaction['running_balance']:
            self.transactions[-2]['txn_msg'] += self.txn_string
            self.txn_string = ''

    def lattice_records(self, constructed_string, row_sorted):
        self.create_transaction(constructed_string)
        try:
            for entry in row_sorted:
                for key, val in bank_parsing_spec[self.bank]['cols_conf'].items():
                    if val[0] <= entry['bbox'][0] <= val[1]:
                        self.current_transaction[key].append(entry)
        except:
            return
        if self.current_transaction['running_balance']:
            self.parse_records()
            if self.txn_string and not self.current_transaction['txn_msg']:
                self.current_transaction['txn_msg'] = self.txn_string
                self.txn_string = ''
            self.transactions.append(self.current_transaction)

    def declare_current_transaction(self):
        self.current_transaction = {
            'txn_date': self.curr_date,
            'txn_msg': [],
            'debit_amount': [],
            'credit_amount': [],
            'running_balance': [],
            'cheque_no': []
        }

    def declare_page_markers(self, page_num):
        if self.bank != '':
            bank_type = self.bank

        if page_num not in bank_parsing_spec[bank_type]['page_conf']:
            page_num = 'default'
        self.start_marker = bank_parsing_spec[bank_type]['page_conf'][page_num]['start_row']
        self.end_marker = bank_parsing_spec[bank_type]['page_conf'][page_num]['end_row']
        self.overall_end_marker = bank_parsing_spec[bank_type]['overall_end_row']

    def unprocessed_transactions(self, address):
        self.character_extraction(address)

        # Since, we always read form left to right, optimize data to be
        # read from left to right.
        # This would help us find the location of different headers.
        # It is also required to find co-ordinates
        remapped = self.remap_characters()
        for page_num in range(1, len(remapped) + 1):
            data_set = []

            for key, val in remapped[page_num].items():
                data_set.append((key, val))

            data_set = sorted(data_set, key=lambda x: -x[0])

            self.declare_page_markers(page_num)

            constructed_string = ''
            self.parse_rows(data_set)
            if constructed_string == self.overall_end_marker:
                break

    def get_transaction_list(self, address, detector_obj):
        self.get_bank(address, detector_obj)
        self.unprocessed_transactions(address)
        self.check_balance()
        transaction_list = []
        for transaction in self.transactions:
            transaction_list_single = self.process_transactions(transaction)
            transaction_list.append(transaction_list_single)
        if bank_parsing_spec[self.bank]['error_flag']:
            return self.remove_extra_append(transaction_list)
        else:
            return [i for i in transaction_list if i]

    def check_balance(self):
        initial_balance = (
                self.parse_float(self.transactions[0]['running_balance']) +
                self.parse_float(self.transactions[0]['debit_amount']) -
                self.parse_float(self.transactions[0]['credit_amount'])
        )
        for transaction in self.transactions:
            if not transaction:
                continue
            try:
                new_balance = initial_balance - self.parse_float(
                    transaction['debit_amount']) + self.parse_float(
                    transaction['credit_amount'])

                if abs(new_balance - self.parse_float(
                        transaction['running_balance'])) > 1E-6:
                    print(new_balance)
                    print(self.parse_float(transaction['running_balance']))
                    print('>>> Date: {:%d-%b-%Y}, Msg: {}, Debit: {}, Credit: {}, Balance: {}'.format(
                            transaction['txn_date'],
                            transaction['txn_msg'],
                            transaction['debit_amount'],
                            transaction['credit_amount'],
                            transaction['running_balance']
                        ))
                    pass

                initial_balance = new_balance
            except:
                pass

    @staticmethod
    def remove_extra_append(transactions):
        del transactions[-1]
        return transactions

    def process_transactions(self, transaction):
        try:
            if (transaction['credit_amount'] ==
                    bank_parsing_spec[self.bank]['null_indicator']):
                amount = -1 * float(transaction['debit_amount'].replace(',', ''))
            else:
                amount = float(transaction['credit_amount'].replace(',', ''))
            transaction_list_single = {
                'date': transaction['txn_date'],
                'chqNo': '',
                'balance': float(
                    transaction['running_balance'].replace(',', '')
                ),
                'narration': transaction['txn_msg'],
                'amount': amount
            }
            return transaction_list_single
        except Exception as e:
            pass

    def get_bank(self, address, detector_obj):
        detector_obj.get_bank_type(address=address)
        self.bank = detector_obj.bank


if __name__ == '__main__':
    detector_obj = BankDetector()
    parser_obj = Parser(detector_obj)
    txns = parser_obj.get_transaction_list('hdfc.pdf', detector_obj)
    for txn in txns:
        if txn is None:
            continue
        print(txn)
    print(len(txns))
