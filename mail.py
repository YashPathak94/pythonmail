import argparse
import base64
from typing import List, ByteString

from pepipost.pepipost_client import PepipostClient
from pepipost.configuration import Configuration
from pepipost.models.send import Send
from pepipost.models.mfrom import From
from pepipost.models.content import Content
from pepipost.models.type_enum import TypeEnum
from pepipost.models.attachments import Attachments
from pepipost.models.personalizations import Personalizations
from pepipost.models.email_struct import EmailStruct
from pepipost.models.settings import Settings
from pepipost.exceptions.api_exception import APIException


class Attachment(object):
    def __init__(self,
                 name: str = None,
                 data: ByteString = None):
        self.name = name
        self.data = data


class EmailDto(object):
    def __init__(self,
                 from_email: str = None,
                 from_name: str = None,
                 to: List[str] = None,
                 cc: List[str] = None,
                 bcc: List[str] = None,
                 reply_to: str = None,
                 subject: str = None,
                 body: str = None,
                 tags: List[str] = None,
                 attachments: List[Attachment] = None):
        self.from_email = from_email
        self.from_name = from_name
        self.type = "html"
        self.to = to
        self.cc = cc
        self.bcc = bcc
        self.reply_to = reply_to
        self.subject = subject
        self.body = body
        self.tags = tags
        self.attachments = attachments

        if self.to is None:
            self.to = []
        else:
            self.to = list(set(self.to))

        if self.bcc is None:
            self.bcc = []
        else:
            self.bcc = list(set(self.bcc))

        if self.cc is None:
            self.cc = []
        else:
            self.cc = list(set(self.cc))

        if self.tags is None:
            self.tags = []
        else:
            self.tags = list(set(self.tags))

        if self.attachments is None:
            self.attachments = []


def validate_mailing_list(cc, bcc, to):
    for email in cc.copy():
        if email in to:
            cc.remove(email)
    for email in bcc.copy():
        if email in to or email in cc:
            bcc.remove(email)
    if len(to) == 0 and len(cc) == 0 and len(bcc) == 0:
        raise Exception("all receiver email info is empty")


def get_personalization(dto):
    validate_mailing_list(dto.cc, dto.bcc, dto.to)
    toList = get_email_structs(dto.to)
    ccList = get_email_structs(dto.cc)
    bccList = get_email_structs(dto.bcc)
    return [Personalizations(to=toList, cc=ccList, bcc=bccList)]


def get_email_structs(emails: List[str]):
    list = []
    for email in emails:
        if len(email.strip()) > 0:
            emailStruct = EmailStruct()
            emailStruct.email = email
            list.append(emailStruct)
    return list


def get_setting():
    settings = Settings(footer=False, click_track=False,
                        open_track=False, hepf=False,
                        unsubscribe_track=True)
    return settings


def get_attachments(dto):
    list = []
    for attachment in dto.attachments:
        name = attachment.name
        content = base64.b64encode(attachment.data).decode()
        list.append(Attachments(content, name))
    return list


def create_email(dto: EmailDto):
    mail = Send()

    from_mail = From(dto.from_email, dto.from_name)

    mail.mfrom = from_mail
    mail.subject = dto.subject

    content = Content()
    content.value = dto.body
    content.mtype = TypeEnum.HTML

    mail.content = [content]
    mail.reply_to = dto.reply_to
    mail.personalizations = get_personalization(dto)
    mail.tags = dto.tags
    mail.settings = get_setting()

    mail.attachments = get_attachments(dto)
    return mail


def send_email(dto: EmailDto, api_key: str):
    send = create_email(dto)
    client = PepipostClient()
    Configuration.api_key = api_key
    Configuration.base_uri = "https://gptmtrans.pepipost.com/v5.1"
    mail_send_controller = client.mail_send
    result = mail_send_controller.create_generatethemailsendrequest(send)
    return result


def test_send(api_key: str):
    from_email = "test.com"
    from_name = "ads test"
    # add your email id in the to list
    to = ["xyz.com"]
    cc = []
    bcc = []
    reply_to = "no-reply@xyz.com"
    subject = "test subject"
    body = "test body"
    attachment = Attachment(name="test-file.txt",
                            data="test data in the attachment file".encode())

    email_dto = EmailDto(
        from_email=from_email,
        from_name=from_name,
        to=to,
        cc=cc,
        bcc=bcc,
        reply_to=reply_to,
        subject=subject,
        body=body,
        attachments=[attachment])
    result = send_email(email_dto, api_key)
    return result



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="script to send email")
    parser.add_argument('-k', dest="api_key",
                        default=None, help="api key for netcore")
    api_key = parser.parse_args().api_key
    try:
        result =  test_send(api_key)
        print(result)
    except APIException as e:
        print(e)

# steps for the setup
# we need to install pepipost library to use this script
# run command to install pepipost library "pip install pepipost" or "pip3 install pepipost"
# command line usage to send a test email "python3 email-sender.py -k <api-key>"
# add your email id in the "to" list in test_send function to send test email
# take reference of "test_send()" function to customise the email according to use case
# to integrate in you code, create object of "EmailDto" and call "send_email(email_dto, api_key)" from your code
