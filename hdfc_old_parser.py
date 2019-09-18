import os
from configs.hdfc_config import hdfc_parsing_spec
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage

# From PDFInterpreter import both PDFResourceManager and PDFPageInterpreter

from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfdevice import PDFDevice

# Import this to raise exception whenever text extraction from PDF is not allowed
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTChar
from pdfminer.converter import PDFPageAggregator

from collections import defaultdict
import datetime
import PyPDF2


class Parser:

    def __init__(self):
        self.char_id = 0
        self.extracted_text = []
        self.page_num = 1
        # Comes into use when HDFC documents are provided with improper lattice division
        self.txn_string = ''

    def if_password_protected(self, address):
        with open(address, mode='rb') as f:
            reader = PyPDF2.PdfFileReader(f)
        if reader.isEncrypted:
            reader.decrypt('password')
        else:
            return

    def increment_char_id(self, xyz):
        self.char_id = xyz + 1

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

    def parse_float(self, input_str):
        if not input_str:
            return 0
        input_str = input_str.replace(',', '')
        return float(input_str)

    def does_range_overlap(self, range_1, range_2):
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

    def get_transaction_list(self, address):
        # Create file pointer
        fp = open(address, 'rb')

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

        # Ok now that we have everything to process a pdf document, lets process it page by page
        for page in PDFPage.create_pages(document):
            # As the interpreter processes the page stored in PDFDocument object
            interpreter.process_page(page)
            # The device renders the layout from interpreter
            layout = device.get_result()
            # Out of the many LT objects within layout, we are interested in LTTextBox and LTTextLine
            for lt_obj in layout:
                if isinstance(lt_obj, LTTextBox):
                    self.fetch_chars(lt_obj)
                if isinstance(lt_obj, LTTextLine):
                    self.fetch_chars(lt_obj)

            self.page_num += 1

        fp.close()

        # Since, we always read form left to right, optimize data to be read from left to right.
        # This would help us find the location of different headers. It is also required to find co-ordinates

        remapped = defaultdict(lambda: defaultdict(list))

        for char_text in self.extracted_text:
            remapped[char_text['page_num']][char_text['bbox'][1]].append(char_text)

        overall_end_marker = hdfc_parsing_spec['transactions_old']['overall_end_row']

        transactions = []

        current_transaction = {
            'txn_date': '',
            'txn_msg': '',
            'debit_amount': '',
            'credit_amount': '',
            'running_balance': ''
        }

        for page_num in range(1, len(remapped) + 1):
            dataset = []

            for key, val in remapped[page_num].items():
                dataset.append((key, val))

            dataset = sorted(dataset, key=lambda x: -x[0])

            if page_num in hdfc_parsing_spec['transactions_old']['page_conf']:
                start_marker = hdfc_parsing_spec['transactions_old']['page_conf'][page_num]['start_row']
                end_marker = hdfc_parsing_spec['transactions_old']['page_conf'][page_num]['end_row']
            else:
                start_marker = hdfc_parsing_spec['transactions_old']['page_conf']['default']['start_row']
                end_marker = hdfc_parsing_spec['transactions_old']['page_conf']['default']['end_row']

            has_started = False
            constructed_string = ''

            for row in dataset:
                row_sorted = sorted(row[1], key=lambda x: x['bbox'][0])
                constructed_string = ''
                prev = row_sorted[0]['bbox'][0]

                for entry in row_sorted:
                    line_no = entry['bbox'][1]
                    if abs(prev - entry['bbox'][0]) < 1e-3:
                        constructed_string += entry['text']
                    else:
                        constructed_string += ' ' + entry['text']

                    prev = entry['bbox'][2]

                # print('{} => {}'.format(line_no, constructed_string))

                if constructed_string.find(end_marker) != -1:
                    # print('PageBreaker')
                    break

                if constructed_string == overall_end_marker:
                    # print('Overall marker')
                    for key, val in current_transaction.items():
                        if isinstance(val, list):
                            if len(val) == 0:
                                current_transaction[key] = ''
                                continue

                            part = ''

                            prev = val[0]['bbox'][0]

                            for entry in val:
                                if abs(prev - entry['bbox'][0]) < 1e-3:
                                    part += entry['text']
                                else:
                                    part += ' ' + entry['text']

                                prev = entry['bbox'][2]

                            current_transaction[key] = part
                    transactions.append(current_transaction)

                    break

                if has_started:
                    if len(constructed_string) >= 10:
                        try:
                            curr_date = datetime.datetime.strptime(
                                constructed_string[:hdfc_parsing_spec['transactions_old']['date_format']['length']],
                                hdfc_parsing_spec['transactions_old']['date_format']['date_string']
                            )
                            # print("date is found", curr_date)
                            current_transaction = {
                                'txn_date': curr_date,
                                'txn_msg': [],
                                'debit_amount': [],
                                'credit_amount': [],
                                'running_balance': [],
                                'cheque_no': []
                            }
                        except:
                            self.txn_string += constructed_string
                            pass

                    try:
                        for entry in row_sorted:
                            for key, val in hdfc_parsing_spec['transactions_old']['cols_conf'].items():
                                if val[0] <= entry['bbox'][0] <= val[1]:
                                    current_transaction[key].append(entry)
                    except:
                        continue

                    if hdfc_parsing_spec['transactions_old']['error_flag']:
                        if current_transaction['debit_amount']:
                            for key, val in current_transaction.items():
                                if isinstance(val, list):
                                    if len(val) == 0:
                                        current_transaction[key] = ''
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

                                    current_transaction[key] = part
                                    if self.txn_string and not current_transaction['txn_msg']:
                                        current_transaction['txn_msg'] = self.txn_string
                                        self.txn_string = ''

                            # print('Current Transaction: {} \n Retainer String: {}'.format(
                            #     current_transaction,
                            #     self.txn_string
                            # ), end='\n\n\n')
                            transactions.append(current_transaction)

                if constructed_string.find(start_marker) >= 0:
                    has_started = True

            if constructed_string == overall_end_marker:
                break

        # print(len(transactions))

        initial_balance = (
                self.parse_float(transactions[0]['running_balance']) +
                self.parse_float(transactions[0]['debit_amount']) -
                self.parse_float(transactions[0]['credit_amount'])
        )

        for txn in transactions:
            # print(txn)
            new_balance = initial_balance - self.parse_float(txn['debit_amount']) + self.parse_float(txn['credit_amount'])

            # if abs(new_balance - self.parse_float(txn['running_balance'])) > 1E-6:
            #     print(new_balance)
            #     print(self.parse_float(txn['running_balance']))
            #     print('>>> Date: {:%d-%b-%Y}, Msg: {}, Debit: {}, Credit: {}, Balance: {}'.format(
            #         txn['txn_date'],
            #         txn['txn_msg'],
            #         txn['debit_amount'],
            #         txn['credit_amount'],
            #         txn['running_balance']
            #     ))

            initial_balance = new_balance

        transaction_list = []
        for transaction in transactions:
            if transaction['credit_amount'] == '0.00':
                amount = -1 * float(transaction['debit_amount'].replace(',', ''))
            else:
                amount = float(transaction['credit_amount'].replace(',', ''))
            transaction_list_single = {
                'date': transaction['txn_date'],
                'chqNo': '',
                'balance': float(transaction['running_balance'].replace(',', '')),
                'narration': transaction['txn_msg'],
                'amount': amount
            }
            transaction_list.append(transaction_list_single)
        del transaction_list[-1]
        return transaction_list

    # def reduce_by_date(self, address, date):
    #     raw_transactions = self.get_transaction_list(address)
    #     for raw_transaction in raw_transactions:
    #         if raw_transaction['date'] < date:
    #             raw_transactions.remove(raw_transaction)
    #             continue
    #     print(len(raw_transactions))


if __name__ == '__main__':
    parser_obj = Parser()
    start_date = datetime.datetime(2019, 2, 1)
    txns = parser_obj.get_transaction_list('hdfc.pdf')
    for txn in txns:
        print('Transaction: {}'.format(txn), end='\n\n')
    print('Length = {}'.format(len(txns)))
