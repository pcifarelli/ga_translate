#!/usr/bin/env python3

import pycurl
import certifi
from google.cloud import translate
import six
import boto3

try:
    # python 3
    from urllib.parse import urlencode
except ImportError:
    # python 2
    from urllib import urlencode

UCDP_hostname   = "rests_translate.ucdp.thomsonreuters.com"
UCDP_port       = 8301
UCDP_ip         = "10.51.13.16"
UCDP_cert       = "ucdp_rests_translate.pem"
UCDP_certpasswd = "password"
    
def google_translate_text(text):
    """Translates text into the target language.

    Target must be an ISO 639-1 language code.
    See https://g.co/cloud/translate/v2/translate-reference#supported_languages
    """
    translate_client = translate.Client()

    if isinstance(text, six.binary_type):
        text = text.decode('utf-8')

    # Text can also be a sequence of strings, in which case this method
    # will return a sequence of results for each text.
    result = translate_client.translate(text, target_language="en")
    
    return result

def amazon_translate_text(text):
    translate_client = boto3.client(service_name='translate', region_name='us-east-1')
    result = translate_client.translate_text(Text=text, SourceLanguageCode="auto", TargetLanguageCode="en")
    return {'input' : text, 'translatedText' : result.get('TranslatedText'), 'detectedSourceLanguage' : result.get('SourceLanguageCode') }
    
def print_results(google_result, amazon_result):
    print(u'Input: {}'.format(google_result['input']))
    print("**************\n")
    print(u'Google Translation: detected {}\n {}'.format(google_result['detectedSourceLanguage'],google_result['translatedText']))
    print("**************\n")
    print(u'Amazon Translation: detected {}\n {}'.format(amazon_result['detectedSourceLanguage'],amazon_result['translatedText']))
    print("**************\n")
   
    
def set_ServerNameIndication(c, hostname, port, ip):
    resolve = hostname + ":" + str(port) + ":" + ip
    c.setopt(c.RESOLVE, [ resolve ] )
    url = "https://" + hostname + ":" + str(port) + "/ucdpext/stream"
    c.setopt(c.URL, url)
    c.setopt(c.SSL_VERIFYPEER, False)

def set_Certificate(c, certificate_filename, password):
    c.setopt(c.SSLCERTTYPE, "PEM")
    c.setopt(c.KEYPASSWD, password)
    c.setopt(c.SSLCERT, certificate_filename)

def set_Postfields(c, post_data ):
    postfields = urlencode(post_data)
    c.setopt(c.POSTFIELDS, postfields)

class MyData:
    def write(self, data):
        # This is the received data from UCDP
        f = open("xinhua.txt", "a+")
        f.seek(0, 2)
        byte_str = data.decode('UTF-8')
        f.write("Length=%d\n" % len(byte_str))
        f.write(byte_str)
        f.close()

def main():
    cn_text = """
    　　新华社莫斯科７月２１日电据俄罗斯外交部网站２１日发布的消息，俄罗斯外长拉夫罗夫与美国国务卿蓬佩奥当天通电话，讨论双边关系等问题。
　　消息说，双方就两国关系发展前景、在平等互利基础上推动双边关系正常化等交换了意见。两人还讨论了叙利亚及其周边局势，并就支持推进朝鲜半岛无核化交换了意见。拉夫罗夫还表示，美方指控并逮捕俄罗斯公民玛丽亚·布蒂娜的行为不可接受，美方应立即将其释放。（完）
    """
    #google_result = google_translate_text(cn_text)
    #amazon_result = amazon_translate_text(cn_text)
    #print_results(google_result, amazon_result)
    
    c = pycurl.Curl()
    c.setopt(c.VERBOSE, True)
    # not strictly needed, except if UCDP ever goes to real certs
    c.setopt(c.CAINFO, certifi.where())
    set_ServerNameIndication(c, UCDP_hostname, UCDP_port, UCDP_ip)
    set_Certificate(c, UCDP_cert, UCDP_certpasswd)
    set_Postfields(c, post_data = { 'compression' : 'none', 'replay' : False } )

    recvr = MyData()
    c.setopt(c.WRITEDATA, recvr)
    try:
        c.perform()
    except:
        print("Stream interrupted")
        c.close()

if __name__ == "__main__":
    main()



