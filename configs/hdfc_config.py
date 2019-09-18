hdfc_parsing_spec = {
    'transactions': {
        'page_conf': {
            1: {
                'start_row': 'Date Narration Chq./Ref.No. Value Dt Withdrawal Amt. Deposit Amt. Closing Balance',
                'end_row': 'HDFC BANK LIMITED'
            },
            'default': {
                'start_row': 'Statement of account',
                'end_row': 'HDFC BANK LIMITED'
            }
        },
        'start_page': 0,
        'overall_end_row': 'STATEMENT SUMMARY :-',
        'cols_conf': {
            'txn_msg': [65.062, 279],
            'debit_amount': [390.947, 470.235],
            'credit_amount': [500, 548.187],
            'running_balance': [550, 626.705],
            'cheque_no': [295, 360]
        },
        'null_indicator': '',
        'date_format': {
            'date_string': '%d/%m/%y',
            'length': 8
        },
        'error_flag': False
    },
    'transactions_old': {
            'page_conf': {
                1: {
                    'start_row': 'Narration Chq. / Ref No. Value Date Withdrawal Amount Deposit Amount Closing Balance*',
                    'end_row': 'Requesting Branch code : SYSTEM'
                },
                'default': {
                    'start_row': 'Statement From',
                    'end_row': 'Requesting Branch code : SYSTEM'
                }
            },
            'start_page': 1,
            'overall_end_row': 'STATEMENT SUMMARY :-',
            'cols_conf': {
                'txn_msg': [70.85, 280],  # Change the coordinates
                'debit_amount': [505, 580],
                'credit_amount': [590, 650],
                'running_balance': [660, 720],
                'cheque_no': [290, 360]
            },
            'null_indicator': '0.00',
            'date_format': {
                'date_string': '%d/%m/%Y',
                'length': 10
            },
            'error_flag': True
        },
    'customer_info': {
        'name': {
            'row': 7
        },
        'email': {
            'row': 'unknown',
            'prefix': 'Email : ',
            'split_by': ':',
            'split_index': 1
        },
        'address': {
            'row': 'unknown',
        },
        'account_no': {

        },
        'ifsc_code': {

        }
    }
}