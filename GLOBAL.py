from QQBot import QQBot
from Logger import Logger
from Text2Speech import Text2Speech
from flask import Flask, request
import json
import requests

with open('conf.json', 'r+', encoding="utf-8") as f:
    content = f.read()
conf = json.loads(content)
t2s = Text2Speech(conf['speech_key'], conf['service_region'], conf['container_name'], conf['connect_str'],
                         conf['error_url'])
s = requests.Session()
logger = Logger()
bot = QQBot()
app = Flask(__name__)