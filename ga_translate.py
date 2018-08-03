#!/usr/bin/env python3


import json
import pycurl
import feedparser
from feedgen.feed import FeedGenerator
import certifi
import untangle
from datetime import datetime, date, timezone
import time
import random
try:
    # python 3
    from urllib.parse import urlencode
except ImportError:
    # python 2
    from urllib import urlencode
#from google.cloud import translate
import six
import boto3

AMAZON_TRANSLATE_LIMIT = 5000

VERBOSE         = False
UCDP_hostname   = "rests_translate.ucdp.thomsonreuters.com"
UCDP_port       = 8301
UCDP_ip         = "10.51.13.15"
UCDP_cert       = "/home/ec2-user/ga_translate/ucdp_rests_translate.pem"
UCDP_certpasswd = "password"
URLROOT         = "http://10.97.21.48/rss"
DOCROOT         = "/var/www/html/rss/"
RSSFEEDFILENAME = "xtest.xml"
RSSTITLE        = "Machine Translation PoC"
RSSDESCRIPTION  = "Test of Chinese Language translation"

EN_ONLY_T       = "/home/ec2-user/ga_translate/html.template.en_only"
CN_ONLY_T       = "/home/ec2-user/ga_translate/html.template.cnh_cnb"
ENH_CNB_T       = "/home/ec2-user/ga_translate/html.template.enh_cnb"
CNH_ENB_T       = "/home/ec2-user/ga_translate/html.template.cnh_enb"


########################################################################################
# UCDPData: Get data from UCDP's REST streamer
########################################################################################
class UCDPData:
    def __init__(self, UCDP_hostname, UCDP_port, UCDP_ip, UCDP_cert, UCDP_certpasswd, verbose):
        self.html = ""
        self.headline = ""
        self.headline_lang = ""
        self.text = ""
        self.html_language = ""
        self.text_language = ""
        self.storydate = None
        
        self._Raw = None
        self._Rsf = ""
        self._json = ""
        self._isTick = False
        self._segments = 0
        self._success = False
        
        self._c = pycurl.Curl()
        self._c.setopt(self._c.VERBOSE, verbose)
        # not strictly needed, except if UCDP ever goes to real certs
        self._c.setopt(self._c.CAINFO, certifi.where())
        self.set_ServerNameIndication(self._c, UCDP_hostname, UCDP_port, UCDP_ip)
        self.set_Certificate(self._c, UCDP_cert, UCDP_certpasswd)
        self.set_Postfields(self._c, post_data = { 'compression' : 'none', 'replay' : False } )

    def set_ServerNameIndication(self, c, hostname, port, ip):
        resolve = hostname + ":" + str(port) + ":" + ip
        c.setopt(c.RESOLVE, [ resolve ] )
        url = "https://" + hostname + ":" + str(port) + "/ucdpext/stream"
        c.setopt(c.URL, url)
        c.setopt(c.SSL_VERIFYPEER, False)

    def set_Certificate(self, c, certificate_filename, password):
        c.setopt(c.SSLCERTTYPE, "PEM")
        c.setopt(c.KEYPASSWD, password)
        c.setopt(c.SSLCERT, certificate_filename)

    def set_Postfields(self, c, post_data ):
        postfields = urlencode(post_data)
        c.setopt(c.POSTFIELDS, postfields)

    def clear(self):
        self.html = ""
        self.headline = ""
        self.headline_lang = ""
        self.text = ""
        self.html_language = ""
        self.text_language = ""
        self.storydate = None
        self._success = False
        
    def write(self, data):
        # This is the received data from UCDP
        self._isTick = False
        self._success = False
        if (self._Raw == None):
            self._Raw = data
        else:
            self._Raw += data
            
        try:
            self._json = json.loads(self._Raw.decode('UTF-8'))
        except:
            pass # may not be complete
            self._segments += 1
        else:
            self._Raw = None
            self._segments = 0
            try:
                self._json['tick']
                self._isTick = True
            except KeyError:
                pass
            finally:
                if (not self._isTick):
                    try:
                        self._Rsf = self._json['data']
                        self.headline_lang = self._json['language']
                        self.headline = self._json['headline']
                        isodate = self._json['storydate']
                        storydate = datetime.strptime(isodate, "%Y-%m-%d %H:%M:%S.%f")
                        self.storydate = datetime(year=storydate.year, month=storydate.month, day=storydate.day,
                                                  hour=storydate.hour, minute=storydate.minute, second=storydate.second,
                                                  microsecond=storydate.microsecond, tzinfo=timezone.utc)
                    except KeyError:
                        print('Unknown json structure encountered in UCDPData')
                    finally:
                        try:
                            obj = untangle.parse(self._Rsf)
                        except:
                            print ("RSF fails to parse")
                        finally:
                            try:
                                storybody = str(obj.newsMessage.itemSet.newsItem.contentSet.inlineXML)
                                try:
                                    storylang = str(obj.newsMessage.itemSet.newsItem.contentSet.inlineXML['xml:lang'])
                                except:
                                    storylang = self.headline_lang
                                finally:
                                    self.html = storybody
                                    self.html_language = storylang
                            except (NameError, AttributeError):
                                pass
                            finally:
                                try:
                                    storybody = str(obj.newsMessage.itemSet.newsItem.contentSet.inlineData.cdata)
                                    try:
                                        storylang = str(obj.newsMessage.itemSet.newsItem.contentSet.inlineData['xml:lang'])
                                    except:
                                        storylang = self.headline_lang
                                    finally:
                                        self.text = storybody
                                        self.text_language = storylang
                                except (NameError, AttributeError):
                                    pass

                    if (self.html == "" and self.text == ""):
                        print ("ERROR: No story body found")
                    else:
                        self._success = True
                        
    def run(self):
        self._c.setopt(self._c.WRITEDATA, self)
        try:
            self._c.perform()
        except:
            print("Stream interrupted")
        self._c.close()
        
    def print_result(self):
        print ("storydate => ", self.storydate)
        print ("headline =>" + self.headline)
        print ("headline_lang =>" + self.headline_lang)

        print ("language =>" + self.text_language)
        print ("body =>\n" + self.text)

########################################################################################
# Translator: Get data from UCDP's REST streamer and translate it using Amazon Translate
#    extends UCDPData
########################################################################################
class Translator(UCDPData):
    def __init__(self, UCDP_hostname, UCDP_port, UCDP_ip, UCDP_cert, UCDP_certpasswd, verbose):
        UCDPData.__init__(self, UCDP_hostname, UCDP_port, UCDP_ip, UCDP_cert, UCDP_certpasswd, verbose)
        self.clear()

    def clear(self):
        self.en_headline = ""
        self.headline_is_translated = False
        self.en_text = ""
        self.body_is_translated = False
        
    def unicode_truncate(self, s, length, encoding='utf-8'):
        encoded = s.encode(encoding)[:length]
        return encoded.decode(encoding, 'ignore')

    def amazon_translate_text(self, text):
        b = bytes(text, 'UTF-8')
        if (len(b) > AMAZON_TRANSLATE_LIMIT):
            text = self.unicode_truncate(text, AMAZON_TRANSLATE_LIMIT)
        
        translate_client = boto3.client(service_name='translate', region_name='us-east-1')
        result = translate_client.translate_text(Text=text, SourceLanguageCode="auto", TargetLanguageCode="en")
        return {'input' : text, 'translatedText' : result.get('TranslatedText'), 'detectedSourceLanguage' : result.get('SourceLanguageCode') }

    #def google_translate_text(text):
    #    """Translates text into the target language.
    #
    #    Target must be an ISO 639-1 language code.
    #    See https://g.co/cloud/translate/v2/translate-reference#supported_languages
    #    """
    #    translate_client = translate.Client()
    #
    #    if isinstance(text, six.binary_type):
    #        text = text.decode('utf-8')
    #
    #    # Text can also be a sequence of strings, in which case this method
    #    # will return a sequence of results for each text.
    #    result = translate_client.translate(text, target_language="en")
    #    
    #    return result
        
    def translate(self):
        if (not self._isTick and self.headline_lang.lower() != "en" and self._success and len(self.headline) > 0):
            en_headline = self.amazon_translate_text(self.headline)
            self.en_headline = en_headline['translatedText']
            self.headline_is_translated = True

        if (not self._isTick and self.text_language.lower() != "en" and self._success and len(self.text) > 0):
            en_text = self.amazon_translate_text(self.text)
            self.en_text = en_text['translatedText']
            self.body_is_translated = True

    def write(self, data):
        UCDPData.write(self, data)
        self.translate()
        
    def print_result(self):
        if (not self._isTick):
            print ("storydate => ", self.storydate)
            print ("headline =>" + self.headline)
            print ("headline_lang =>" + self.headline_lang)
            if (self.headline_is_translated):
                print (u'Translation:\n{}\n'.format(self.en_headline))

            print ("language =>" + self.text_language)
            print ("body =>\n" + self.text)
            if (self.body_is_translated):
                print (u'Translation:\n{}\n'.format(self.en_text))

########################################################################################
# MyRSSFeed: make an RSS feed
########################################################################################
class myRSSFeed:
    def __init__(self, feed, title, description, urlroot, docroot = "./rss", maxitems = 100):
        self._maxitems = maxitems
        self._items = 0
        self._title = title
        self._description = description
        self._docroot = docroot
        self._urlroot = urlroot
        self._feed = feed
        self._fg = FeedGenerator()
        # make sure we have a "/" at the end of the urlroot
        plen = len(self._urlroot)
        if self._urlroot[plen-1:] != "/":
            self._urlroot += "/"
        # make sure we have a "/" at the end of the docroot
        plen = len(self._docroot)
        if self._docroot[plen-1:] != "/":
            self._docroot += "/"
        self._fg.id(self._urlroot + self._feed)
        self._fg.link( href="\"" + self._urlroot + self._feed + "\"")
        self._fg.description(description)
        self._fg.title(title)
        self.reopen_feed()

    def get_fname(self):
        dt = datetime.now()
        ts = time.mktime(dt.timetuple())
        rn = random.randint(0,10001)
        return (u'{}'.format(int(ts)) + "_" + str(rn) + ".html")

    def update_feed(self, fname, date, title, description):
        if (self._items == self._maxitems):
            # remove the oldest item
            self._fg.remove_item(self._items - 1)
            self._items -= 1
        
        self._items += 1
        fe = self._fg.add_entry()
        fe.id(self._urlroot + fname)
        fe.title(title)
        fe.description(description)
        fe.link(href=self._urlroot + fname)
        fe.pubDate(date)
        self._fg.rss_file(self._docroot + self._feed)
        
    def add_item(self, date, headline, body, htmltemplate):
        try:
            f = open(htmltemplate, "r")
            self._template = f.read()
            f.close()
        except:
            self._template = htmltemplate
            
        fname = self.get_fname()
        f = open(self._docroot + fname, "w")
        fmt = self._template
        f.write(fmt.format(headline, 
                           date.strftime("%Y-%m-%d %H:%M:%S"), 
                           body))
        f.close()
        self.update_feed(fname, date, headline, body)
       
    def reopen_feed(self):
        d = feedparser.parse(self._docroot + self._feed)
        n = min(self._maxitems,len(d.entries))
        for i in reversed(range(n)):
            fe = self._fg.add_entry()
            fe.id(d.entries[i].guid)
            fe.title(d.entries[i].title)
            fe.description(d.entries[i].description)
            fe.link(href=d.entries[i].link)
            fe.pubDate(d.entries[i].published)
            self._items += 1


class ChineseRSSFeed(myRSSFeed):
    def __init__(self, en_only_t, cn_only_t, enh_cnb_t, cnh_enb_t, 
                 feed, title, description, urlroot, docroot = "./rss", maxitems = 100):
        myRSSFeed.__init__(self,feed, title, description, urlroot, docroot, maxitems)
        try:
            f = open(en_only_t, "r")
            self._en_only_template = f.read()
            f.close()
        except:
            self._en_only_template = en_only_t

        try:
            f = open(cn_only_t, "r")
            self._cn_only_template = f.read()
            f.close()
        except:
            self._cn_only_template = cn_only_t

        try:
            f = open(enh_cnb_t, "r")
            self._enh_cnb_template = f.read()
            f.close()
        except:
            self._enh_cnb_template = enh_cnb_t

        try:
            f = open(cnh_enb_t, "r")
            self._cnh_enb_template = f.read()
            f.close()
        except:
            self._cnh_enb_template = cnh_enb_t

    def add_en_only_item(self, date, en_headline, en_body):
        fname = self.get_fname()
        f = open(self._docroot + fname, "w")
        fmt = self._en_only_template
        f.write(fmt.format(en_headline, 
                           date.strftime("%Y-%m-%d %H:%M:%S"), 
                           en_body))
        f.close()
        self.update_feed(fname, date, en_headline, en_body)
    
    def add_cn_only_item(self, date, cn_headline, en_headline, cn_body, en_body):
        fname = self.get_fname()
        f = open(self._docroot + fname, "w")
        fmt = self._cn_only_template
        f.write(fmt.format(cn_headline, 
                           en_headline, 
                           date.strftime("%Y-%m-%d %H:%M:%S"), 
                           cn_body, 
                           en_body))
        f.close()
        self.update_feed(fname, date, en_headline, en_body)
        
    def add_enh_cnb_item(self, date, en_headline, cn_body, en_body):
        fname = self.get_fname()
        f = open(self._docroot + fname, "w")
        fmt = self._enh_cnb_template
        f.write(fmt.format(en_headline, 
                           date.strftime("%Y-%m-%d %H:%M:%S"), 
                           cn_body, 
                           en_body))
        f.close()
        self.update_feed(fname, date, en_headline, en_body)
        
    def add_cnh_enb_item(self, date, cn_headline, en_headline, en_body):
        fname = self.get_fname()
        f = open(self._docroot + fname, "w")
        fmt = self._cnh_enb_template
        f.write(fmt.format(cn_headline,
                           en_headline, 
                           date.strftime("%Y-%m-%d %H:%M:%S"), 
                           en_body))
        f.close()
        self.update_feed(fname, date, en_headline, en_body)
        
        
########################################################################################
# XinuaTranslatorRSS: 
# Get data from UCDP's REST streamer, translate if needed, make into RSS feed
########################################################################################
class XinhuaTranslatorRSS(Translator):
    def __init__(self,  
                 rssfeedfilename, 
                 rsstitle, 
                 rssdescription, 
                 rssurlroot, 
                 rssdocroot, 
                 rssmaxitems, 
                 UCDP_hostname, 
                 UCDP_port, 
                 UCDP_ip, 
                 UCDP_cert, 
                 UCDP_certpasswd, 
                 verbose):
        Translator.__init__(self, 
                            UCDP_hostname, 
                            UCDP_port, 
                            UCDP_ip, 
                            UCDP_cert, 
                            UCDP_certpasswd, 
                            verbose);
        self._rss = ChineseRSSFeed(EN_ONLY_T, 
                                   CN_ONLY_T, 
                                   ENH_CNB_T, 
                                   CNH_ENB_T,
                                   rssfeedfilename, 
                                   rsstitle, 
                                   rssdescription, 
                                   rssurlroot,
                                   rssdocroot,
                                   rssmaxitems)
        
    def write(self, data):
        Translator.write(self, data)
        if (not self._isTick and self._success):
            if (self.headline_is_translated and self.body_is_translated):
                self._rss.add_cn_only_item(self.storydate, self.headline, self.en_headline, self.text, self.en_text)
            elif (self.headline_is_translated and not self.body_is_translated):
                self._rss.add_cnh_enb_item(self.storydate, self.headline, self.en_headline, self.text)
            elif (not self.headline_is_translated and self.body_is_translated):
                self._rss.add_enh_cnb_item(self.storydate, self.headline, self.text, self.en_text)
            else:
                self._rss.add_en_only_item(self.storydate, self.headline, self.text)
            Translator.clear(self)
            UCDPData.clear(self)
    
    
def main():
    rss_generator = XinhuaTranslatorRSS(  
                     rssfeedfilename = RSSFEEDFILENAME, 
                     rsstitle        = RSSTITLE, 
                     rssdescription  = RSSDESCRIPTION, 
                     rssurlroot      = URLROOT, 
                     rssdocroot      = DOCROOT, 
                     rssmaxitems     = 100, 
                     UCDP_hostname   = UCDP_hostname, 
                     UCDP_port       = UCDP_port, 
                     UCDP_ip         = UCDP_ip, 
                     UCDP_cert       = UCDP_cert, 
                     UCDP_certpasswd = UCDP_certpasswd, 
                     verbose         = VERBOSE)
    rss_generator.run()

if __name__ == "__main__":
    main()



