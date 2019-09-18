import os
from configs.hdfc_config import hdfc_parsing_spec
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
import arrow
import mpu.io

# From PDFInterpreter import both PDFResourceManager and PDFPageInterpreter

from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfdevice import PDFDevice

# Import this to raise exception whenever text extraction from PDF is not allowed
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTChar
from pdfminer.converter import PDFPageAggregator

from collections import defaultdict
import datetime

# Create file pointer
fp = open('hdfc.pdf', 'rb')

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

char_id = 0

extracted_text = []

page_num = 1


def increment_char_id(xyz):
    global char_id
    char_id = xyz + 1


def fetch_chars(lt_obj):
    if isinstance(lt_obj, LTChar):
        extracted_text.append({
            'bbox': lt_obj.bbox,
            'page_num': page_num,
            'text': lt_obj.get_text(),
            'char_id': char_id
        })

        increment_char_id(char_id)

    if not hasattr(lt_obj, '_objs'):
        return

    objs = lt_obj._objs

    if not objs:
        return

    for obj in objs:
        fetch_chars(obj)


# Ok now that we have everything to process a pdf document, lets process it page by page
for page in PDFPage.create_pages(document):
    # As the interpreter processes the page stored in PDFDocument object
    interpreter.process_page(page)
    # The device renders the layout from interpreter
    layout = device.get_result()
    # Out of the many LT objects within layout, we are interested in LTTextBox and LTTextLine
    for lt_obj in layout:
        if isinstance(lt_obj, LTTextBox):
            fetch_chars(lt_obj)
        if isinstance(lt_obj, LTTextLine):
            fetch_chars(lt_obj)

    page_num += 1

fp.close()

# Since, we always read form left to right, optimize data to be read from left to right.
# This would help us find the location of different headers. It is also required to find co-ordinates

remapped = defaultdict(lambda: defaultdict(list))

for char_text in extracted_text:
    remapped[char_text['page_num']][char_text['bbox'][1]].append(char_text)

overall_end_marker = hdfc_parsing_spec['transactions']['overall_end_row']

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

    if page_num in hdfc_parsing_spec['transactions']['page_conf']:
        start_marker = hdfc_parsing_spec['transactions']['page_conf'][page_num]['start_row']
        end_marker = hdfc_parsing_spec['transactions']['page_conf'][page_num]['end_row']
    else:
        start_marker = hdfc_parsing_spec['transactions']['page_conf']['default']['start_row']
        end_marker = hdfc_parsing_spec['transactions']['page_conf']['default']['end_row']

    has_started = False

    for row in dataset:
        row_sorted = sorted(row[1], key=lambda x: x['bbox'][0])
        constructed_string = ''

        prev = row_sorted[0]['bbox'][0]

        for entry in row_sorted:
            # print(entry, end='\n\n\n\n')
            if abs(prev - entry['bbox'][0]) < 1e-3:
                constructed_string += entry['text']
            else:
                constructed_string += ' ' + entry['text']

            prev = entry['bbox'][2]

        # print(constructed_string)

        if constructed_string == end_marker:
            break

        if constructed_string == overall_end_marker:
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
            # print(constructed_string)

            if len(constructed_string) >= 8:
                try:
                    curr_date = datetime.datetime.strptime(
                        constructed_string[:hdfc_parsing_spec['transactions']['date_format']['length']],
                        hdfc_parsing_spec['transactions']['date_format']['date_string']
                    )

                    if current_transaction['txn_msg']:
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

                    current_transaction = {
                        'txn_date': curr_date,
                        'txn_msg': [],
                        'debit_amount': [],
                        'credit_amount': [],
                        'running_balance': [],
                        'cheque_no': []
                    }
                except:
                    pass

            for entry in row_sorted:
                for key, val in hdfc_parsing_spec['transactions']['cols_conf'].items():
                    if val[0] <= entry['bbox'][0] <= val[1]:
                        current_transaction[key].append(entry)

        if constructed_string == start_marker:
            has_started = True

    if constructed_string == overall_end_marker:
        break


def parse_float(input_str):
    if not input_str:
        return 0

    input_str = input_str.replace(',', '')
    return float(input_str)


initial_balance = (
        parse_float(transactions[0]['running_balance']) +
        parse_float(transactions[0]['debit_amount']) -
        parse_float(transactions[0]['credit_amount'])
)

for txn in transactions:
    new_balance = initial_balance - parse_float(txn['debit_amount']) + parse_float(txn['credit_amount'])

    if abs(new_balance - parse_float(txn['running_balance'])) > 1E-6:
        print(new_balance)
        print(parse_float(txn['running_balance']))
        print('>>> Date: {:%d-%b-%Y}, Msg: {}, Debit: {}, Credit: {}, Balance: {}'.format(
            txn['txn_date'],
            txn['txn_msg'],
            txn['debit_amount'],
            txn['credit_amount'],
            txn['running_balance']
        ))

    initial_balance = new_balance


def does_range_overlap(range_1, range_2):
    if range_1[1] < range_2[0]:
        return False

    if range_1[0] > range_2[1]:
        return False

    return True


def find_texts_in_row(page_num, word_range):
    overlapping_texts = []

    for text in extracted_text:
        if text['page_num'] != page_num:
            continue

        if does_range_overlap(word_range, (text['bbox'][1], text['bbox'][3])):
            overlapping_texts.append(text)

    return overlapping_texts


transaction_list = []
for transaction in transactions:
    if transaction['credit_amount'] == '':
        amount = float(transaction['debit_amount'].replace(',',''))
    else:
        amount = -1 * float(transaction['credit_amount'].replace(',',''))
    transaction_list_single = {
            'date': transaction['txn_date'],
            'chqNo': '',
            'balance': float(transaction['running_balance'].replace(',','')),
            'narration': transaction['txn_msg'],
            'amount': amount
        }
    transaction_list.append(transaction_list_single)

for transaction in transaction_list:
    print(transaction)
print(len(transaction_list))

# {'date': '2019-06-07',
#    'chqNo': '',
#    'amount': '-2000.00',
#    'balance': '56.00',
#    'category': 'Cash Withdrawal',
#    'narration': 'NWD-541919XXXXXX2674-N3622400-MUMBAI (Ref# 915816802036)'}
