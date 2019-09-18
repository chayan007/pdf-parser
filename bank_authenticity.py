from PyPDF2 import PdfFileReader


class BankAuthenticator:

    def __init__(self):
        self.flag = 0

    @staticmethod
    def get_info(address):
        with open(address, 'rb') as f:
            pdf = PdfFileReader(f)
            if pdf.isEncrypted:
                pdf.decrypt('')
                info = pdf.getDocumentInfo()
        return info


if __name__ == '__main__':
    auth_obj = BankAuthenticator()
    path = 'hdfc_longest.pdf'
    information = auth_obj.get_info(path)
    print('Author: {}'.format(information.author))
    print('Creator: {}'.format(information.creator))
    print('Producer: {}'.format(information.producer))
    print('Subject: {}'.format(information.subject))
    print('Title: {}'.format(information.title))
