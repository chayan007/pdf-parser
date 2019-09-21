from PyPDF2 import PdfFileReader


class BankAuthenticator:

    def __init__(self):
        self.flag = 0

    @staticmethod
    def get_info(address):
        with open(address, 'rb') as f:
            pdf = PdfFileReader(f)
            if pdf.isEncrypted:
                pass
            info = pdf.getDocumentInfo()
        return info

    def check_if_password_protected(self, address):
        with open(address, mode='rb') as f:
            reader = PdfFileReader(f)
        if reader.isEncrypted:
            reader.decrypt('hoge1234')
        self.get_info(address)


if __name__ == '__main__':
    auth_obj = BankAuthenticator()
    path = 'hdfc.pdf'
    information = auth_obj.get_info(path)
    print('Author: {}'.format(information.author))
    print('Creator: {}'.format(information.creator))
    print('Producer: {}'.format(information.producer))
    print('Subject: {}'.format(information.subject))
    print('Title: {}'.format(information.title))
