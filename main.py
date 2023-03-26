import json
import os
import re
import copy

import requests
from flask import Flask, request
from time import sleep
import threading
# import openai
# from dotenv import load_dotenv
from datetime import datetime
import azure.cognitiveservices.speech as speechsdk
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.cognitiveservices.speech import SpeechSynthesisOutputFormat
import pysilk
# from azure.identity import DefaultAzureCredential


# load_dotenv()
# openai.api_key = os.getenv("OPENAI_API_KEY")

class Logger:
    def __init__(self, level='debug'):
        self.level = level

    def DebugLog(self, *args):
        if self.level == 'debug':
            print(*args)

    def TraceLog(self, *args):
        if self.level == 'trace':
            print(*args)

    def setDebugLevel(self, level):
        self.level = level.lower()

# ref: https://github.com/MicrosoftDocs/azure-docs.zh-cn/blob/master/articles/cognitive-services/Speech-Service/speech-synthesis-markup.md
# ref2: https://learn.microsoft.com/zh-tw/dotnet/api/microsoft.cognitiveservices.speech.speechsynthesisoutputformat?view=azure-dotnet#fields
class Text2Speech:
    def __init__(self, speech_key, service_region, container_name, connect_str, error_url, set_speech_synthesis_output_format=SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm, Dir='./SpeechResources/'):
        self.speech_key = speech_key
        self.service_region = service_region
        self.container_name = container_name
        self.connect_str = connect_str
        self.error_url = error_url
        self.set_speech_synthesis_output_format = set_speech_synthesis_output_format
        self.dir = Dir
        self.error_audio = error_url
        self.file_dir = "./SpeechResources/"
        self.file_name = "error.silk"
    def getVoice(self, text):
        if text == None or text == "":
            return self.file_dir + self.file_name
        speech_config = speechsdk.SpeechConfig(subscription=self.speech_key, region=self.service_region)
        speech_config.set_speech_synthesis_output_format(self.set_speech_synthesis_output_format)
        speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)

        ssml = """
                <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
                       xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="zh-CN">
                    <voice name="zh-CN-XiaoyiNeural">
                        <mstts:express-as role="Girl" style="disgruntled" styledegree="5">
                            <prosody contour="(60%,-60%) (100%,+80%)">
                            """ + text + """
                            </prosody>
                        </mstts:express-as>
                    </voice>
                </speak>
                """
        result = speech_synthesizer.speak_ssml_async(ssml).get()
        audio_name = "Audio" + datetime.now().strftime("%Y%m%d%H%M%S")
        with open(self.dir + audio_name + ".pcm", 'wb') as audio_file:
            audio_file.write(result.audio_data)
        #convert from pcm to silk
        with open(self.dir + audio_name + ".pcm", "rb") as pcm, open(self.dir + audio_name + ".silk", "wb") as silk:
            pysilk.encode(pcm, silk, 24000, 24000)

        # Checks result.
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print("Speech synthesized to speaker for text [{}]".format(text))
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print("Speech synthesis canceled: {}".format(cancellation_details.reason))
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                if cancellation_details.error_details:
                    print("Error details: {}".format(cancellation_details.error_details))
            print("Did you update the subscription info?")
        audio_name = audio_name + ".silk"
        self.file_dir = self.dir
        self.file_name = audio_name
        if os.path.exists(self.dir + audio_name):
            return self.dir + audio_name, audio_name
        else:
            return self.error_audio, "error.silk"
    def upload(self, file_dir=None, file_name=None):
        blob_service_client = BlobServiceClient.from_connection_string(self.connect_str)
        blob_client = blob_service_client.get_blob_client(container=self.container_name, blob=self.file_name)
        with open(file=self.file_dir + self.file_name, mode="rb") as data:
            try:
                blob_client.upload_blob(data)
                return blob_client.url
            except:
                return self.error_audio
            # blob_client.get_blob_properties()
            # print(result)
            # print(blob_client.url)
        return self.error_audio

class QQBot:
    def __init__(self):
        self.addr = 'http://127.0.0.1:8080/'
        self.session = None

    def verifySession(self, auth_key):
        """每个Session只能绑定一个Bot，但一个Bot可有多个Session。
		session Key在未进行校验的情况下，一定时间后将会被自动释放"""
        data = {"verifyKey": auth_key}
        url = self.addr + 'verify'
        res = requests.post(url, data=json.dumps(data)).json()
        logger.DebugLog(res)
        if res['code'] == 0:
            return res['session']
        return None

    def bindSession(self, session, qq):
        """校验并激活Session，同时将Session与一个已登录的Bot绑定"""
        data = {"sessionKey": session, "qq": qq}
        url = self.addr + 'bind'
        res = requests.post(url, data=json.dumps(data)).json()
        logger.DebugLog(res)
        if res['code'] == 0:
            self.session = session
            return True
        return False

    def releaseSession(self, session, qq):
        """不使用的Session应当被释放，长时间（30分钟）未使用的Session将自动释放，
		否则Session持续保存Bot收到的消息，将会导致内存泄露(开启websocket后将不会自动释放)"""
        data = {"sessionKey": session, "qq": qq}
        url = self.addr + 'release'
        res = requests.post(url, data=json.dumps(data)).json()
        logger.DebugLog(res)
        if res['code'] == 0:
            return True
        return False

    def getMsgFromGroup(self, session):
        url = self.addr + 'fetchLatestMessage?count=10&sessionKey=' + session
        res = requests.get(url).json()
        if res['code'] == 0:
            return res['data']
        return None

    def parseGroupMsg(self, data):
        res = []
        if data is None:
            return res
        for item in data:
            if item['type'] == 'GroupMessage':
                type = item['messageChain'][-1]['type']
                if type == 'Image':
                    text = item['messageChain'][-1]['url']
                elif type == 'Plain':
                    text = item['messageChain'][-1]['text']
                elif type == 'Face':
                    text = item['messageChain'][-1]['faceId']
                else:
                    logger.TraceLog(">> 当前消息类型暂不支持转发：=> " + type)
                    continue
                name = item['sender']['memberName']
                group_id = str(item['sender']['group']['id'])
                group_name = item['sender']['group']['name']
                res.append({'text': text, 'type': type, 'name': name, 'groupId': group_id, 'groupName': group_name})
        return res

    def checkAtBot(self, data, BotQQ):
        if data is None:
            return 0
        for item in data:
            if item['type'] == 'GroupMessage':
                for item2 in item['messageChain']:
                    type = item2['type']
                    # print(type)
                    # if type == 'At':
                        # print(type, item2['target'], BotQQ)
                        # print(type(item2['target']), type(BotQQ))
                    if type == 'At' and str(item2['target'])==str(BotQQ):
                        return 1
        return 0

    def checkOrder(self, data):
        pattern = r'^[ ]*\/[0-9a-zA-Z_]+'
        if data is None:
            return 0
        for item in data:
            if item['type'] == 'GroupMessage':
                for item2 in item['messageChain']:
                    type = item2['type']
                    if type == 'Plain':
                        matches = re.findall(pattern,item2['text'],re.MULTILINE)
                        # print("matches", matches)
                        if len(matches) > 0:
                            return 1, matches[0].split('/')[1]
                    # print(type)
        return 0, ''

    def getMessageCount(self, session):
        url = self.addr + 'countMessage?sessionKey=' + session
        res = requests.get(url).json()
        if res['code'] == 0:
            return res['data']
        return 0

    def sendMsgToGroup(self, session, group, msg):
        text = msg['text']
        type = msg['type']
        name = msg['name']
        group_id = msg['groupId']
        group_name = msg['groupName']
        content1 = "【消息中转助手】\n用户：{}\n群号：{}\n群名：{}\n消息：\n{}".format(
            name, group_id, group_name, text)
        content2 = "【消息中转助手】\n用户：{}\n群号：{}\n群名：{}\n消息：\n".format(
            name, group_id, group_name)
        logger.DebugLog(">> 消息类型：" + type)
        if type == 'Plain':
            message = [{"type": type, "text": content1}]
        elif type == 'Image':
            message = [
                {"type": 'Plain', "text": content2},
                {"type": type, "url": text}]
        elif type == 'Face':
            message = [{"type": 'Plain', "text": content2},
                       {"type": type, "faceId": text}]
        else:
            logger.TraceLog(">> 当前消息类型暂不支持转发：=> " + type)
            return 0
        data = {
            "sessionKey": session,
            "group": group,
            "messageChain": message
        }
        logger.DebugLog(">> 消息内容：" + str(data))
        url = self.addr + 'sendGroupMessage'
        try:
            res = requests.post(url, data=json.dumps(data)).json()
        except:
            logger.DebugLog(">> 转发失败")
            return 0
        logger.DebugLog(">> 请求返回：" + str(res))
        if res['code'] == 0:
            return res['messageId']
        return 0

    def ReplyMsgToGroup(self, session, msg, ReplyMsgId):
        text = msg['text']
        type = msg['type']
        name = msg['name']
        group_id = msg['groupId']
        group_name = msg['groupName']
        content1 = "收到\n用户：{}\n群号：{}\n群名：{}\n消息：\n{}".format(
            name, group_id, group_name, text)
        content2 = "收到\n用户：{}\n群号：{}\n群名：{}\n消息：\n".format(
            name, group_id, group_name)
        content3 = ""
        # if type == "Plain":
        #     print("text={}".format(text))
        #     response = openai.Completion.create(
        #         model="text-davinci-003",
        #         prompt="你好",
        #         temperature=1,
        #         max_tokens=60,
        #     )
        #     content3 = response["choices"][0]["text"]
        #     print(response)
        #     print(content3)
        if type == 'Plain':
            content3, tmout = getGPTMsg("你是一个可爱的猫娘，你会傲娇地回答问题：", text)

        logger.DebugLog(">> 消息类型：" + type)
        if type == 'Plain':
            # message = [{"type": type, "text": content1 + '\n' + content3}]
            message = [{"type": type, "text": content3}]
        elif type == 'Image':
            message = [
                {"type": 'Plain', "text": content2},
                {"type": type, "url": text}]
        elif type == 'Face':
            message = [{"type": 'Plain', "text": content2},
                       {"type": type, "faceId": text}]
        else:
            logger.TraceLog(">> 当前消息类型暂不支持回复：=> " + type)
            return 0
        data = {
            "sessionKey": session,
            "group": group_id,
            'quote': ReplyMsgId,
            "messageChain": message
        }
        logger.DebugLog(">> 消息内容：" + str(data))
        url = self.addr + 'sendGroupMessage'
        try:
            res = requests.post(url, data=json.dumps(data)).json()
        except:
            logger.DebugLog(">> 回复失败")
            return 0
        logger.DebugLog(">> 请求返回：" + str(res))
        if res['code'] == 0:
            return res['messageId']
        return 0

    def revokeMsgGroup(self, session, target, msgId):
        data = {
            "sessionKey": session,
            "target": target,
            'messageId': msgId
        }
        logger.DebugLog(">> 撤回消息：" + str(msgId))
        url = self.addr + 'recall'
        try:
            res = requests.post(url, data=json.dumps(data)).json()
        except:
            logger.DebugLog(">> 撤回失败")
            return 0
        logger.DebugLog(">> 请求返回：" + str(res))
        if res['code'] == 0:
            return res['msg']

    def muteMemberGroup(self, session, target, memberId, mute_time=86400):
        data = {
            "sessionKey": session,
            "target": target,
            "memberId": memberId,
            'time': mute_time
        }
        logger.DebugLog(">> 禁言成员：" + str(memberId))
        url = self.addr + 'mute'
        try:
            res = requests.post(url, data=json.dumps(data)).json()
        except:
            logger.DebugLog(">> 禁言失败")
            return 0
        logger.DebugLog(">> 请求返回：" + str(res))
        if res['code'] == 0:
            return res['msg']

    def ReplyOrder(self, session, msg, order, order_list, msg_chain, ReplyMsgId):
        global voice_url
        text = msg['text']
        type = msg['type']
        name = msg['name']
        group_id = msg['groupId']
        group_name = msg['groupName']
        content = ""
        revoke_name, ban_name = "", ""
        quote_id = 0
        voice_url = "./SpeechResources/error.mp3"
        if type != 'Plain':
            return 0
        if order not in order_list:
            content = "Your order is not in the order list. Enter /h to get more information."
        else:
            if order == "h":
                content = "◆ Order List:\n" + "\n".join(str(i) for i in order_list)
            elif order == "whoami":
                content = "I'm a bot Powered by Mirai-Core, and my author is Phinney."
            elif order == "revoke":
                revoke_name, quote_id = getReplyMsgId(msg_chain)
                bot.revokeMsgGroup(session, group_id, quote_id)
                content = name + "认为" + revoke_name + "发送了不当内容，已予以撤回。如有疑问请联系管理员处理。"
            elif order == "kick":
                kick_name, quote_id = getReplyMsgId(msg_chain)
                bot.revokeMsgGroup(session, group_id, quote_id)
                bot.muteMemberGroup(session, int(group_id), int(kick_name))
                content = name + "认为" + kick_name + "发送了不当内容，已予以撤回并禁言。如有疑问请联系管理员处理。"
            elif order == "speak":
                try:
                    question_text = text.split('/speak', 1)[1]
                    voice_text, tmout = getGPTMsg("你是一个可爱的猫娘，你会傲娇地回答问题：", question_text)
                except:
                    voice_text = ""
                if tmout == 1:
                    voice_text = ""
                t2s.getVoice(voice_text)
                voice_url = t2s.upload()
                # print("=====================>")
                # print(voice_text)
                # print(voice_url)
                # print("=====================>")
            elif order == "repeat":
                # print("ORDER: REPEAT",text)
                try:
                    voice_text = text.split('/repeat', 1)[1]
                    # print("repeat:",voice_text)
                except:
                    voice_text = ""
                t2s.getVoice(voice_text)
                voice_url = t2s.upload()
            else:
                content = "Unknown Error."
                logger.DebugLog(">> 当前命令类型暂不支持回复：=> " + order)

        # if type == 'Plain':
        #     response = getGPTMsg("你是一个可爱的猫娘，你会傲娇地回答问题：", text)
        #     content = response["choices"][0]["message"]["content"]

        logger.DebugLog(">> 消息类型：" + type)
        if type == 'Plain':
            # message = [{"type": type, "text": content1 + '\n' + content3}]
            message = [{"type": type, "text": content}]
        else:
            logger.TraceLog(">> 当前消息类型暂不支持回复：=> " + type)
            return 0
        # important!!!
        if order == 'speak' or order == 'repeat':
            message = [{"type": "Voice", "url": voice_url}]
        data = {
            "sessionKey": session,
            "group": group_id,
            'quote': ReplyMsgId,
            "messageChain": message
        }
        logger.DebugLog(">> 消息内容：" + str(data))
        url = self.addr + 'sendGroupMessage'
        try:
            res = requests.post(url, data=json.dumps(data)).json()
        except:
            logger.DebugLog(">> 回复失败")
            return 0
        logger.DebugLog(">> 请求返回：" + str(res))
        if res['code'] == 0:
            return res['messageId']
        return 0

    def sendMsgToAllGroups(self, session, receive_groups, send_groups, msg_data):
        # 对每条消息进行检查
        for msg in msg_data:
            group_id = msg['groupId']
            # 接收的消息群正确（目前只支持 消息类型）
            if group_id in receive_groups:
                # 依次将消息转发到目标群
                for g in send_groups:
                    logger.DebugLog(">> 当前群：" + g)
                    if g == group_id:
                        logger.DebugLog(">> 跳过此群")
                        continue
                    res = self.sendMsgToGroup(session, g, msg)
                    if res != 0:
                        logger.TraceLog(">> 转发成功！{}".format(g))

    def ReplySuperFriend(self, session, msg_chain, qq):
        text = ""
        for msg in msg_chain:
            if msg['type'] == 'Plain':
                text = msg['text']
        logger.DebugLog("Super User: {}".format(text))
        reply_msg, tmout = getGPTMsg("你是一个尽心尽力为主人排忧解难的优秀助手", text, "gpt-4", 500, 60)
        if tmout == 1:
            reply_msg = "抱歉，接口响应有些久哦~请等一会再试试吧！[TIME_OUT]"
        logger.DebugLog("GPT Reply: {}".format(reply_msg))
        data = {
            "sessionKey": session,
            "target": qq,
            "messageChain": [
                {"type": "Plain", "text": reply_msg},
            ]
        }
        url = self.addr + 'sendFriendMessage'
        try:
            res = requests.post(url, data=json.dumps(data)).json()
        except:
            logger.DebugLog(">> 发送失败")
            return 0
        if res['code'] == 0:
            return res['messageId']
        return 0

    def sendFriendMessage(self, session, qq, msg):
        data = {
            "sessionKey": session,
            "target": qq,
            "messageChain": [
                {"type": "Plain", "text": msg},
            ]
        }
        url = self.addr + 'sendFriendMessage'
        try:
            res = requests.post(url, data=json.dumps(data)).json()
        except:
            logger.DebugLog(">> 发送失败")
            return 0
        if res['code'] == 0:
            return res['messageId']
        return 0


logger = Logger()
bot = QQBot()
app = Flask(__name__)

# def qqTransfer():
#     with open('conf.json', 'r+', encoding="utf-8") as f:
#         content = f.read()
#     conf = json.loads(content)
#
#     auth_key = conf['auth_key']
#     bind_qq = conf['bind_qq']
#     sleep_time = conf['sleep_time']
#     debug_level = conf['debug_level']
#
#     receive_groups = conf['receive_groups']
#     send_groups = conf['send_groups']
#
#     logger.setDebugLevel(debug_level)
#
#     session = bot.verifySession(auth_key)
#     logger.DebugLog(">> session: " + session)
#     bot.bindSession(session, bind_qq)
#     while True:
#         cnt = bot.getMessageCount(session)
#         if cnt:
#             logger.DebugLog('>> 有消息了 => {}'.format(cnt))
#             logger.DebugLog('获取消息内容')
#             data = bot.getMsgFromGroup(session)
#             if len(data) == 0:
#                 logger.DebugLog('消息为空')
#                 continue
#             logger.DebugLog(data)
#             logger.DebugLog('解析消息内容')
#             data = bot.parseGroupMsg(data)
#             logger.DebugLog(data)
#             logger.DebugLog('转发消息内容')
#             bot.sendMsgToAllGroups(session, receive_groups, send_groups, data)
#         # else:
#         #	 logger.DebugLog('空闲')
#         sleep(sleep_time)
#     bot.releaseSession(session, bind_qq)

def getGPTMsg(GodMsg="", Msg="", gpt_model="gpt-3.5-turbo", max_tokens=200, max_time=20):
    if Msg == "":
        return "抱歉，人家暂时没想好该怎么回答你哦~[TIME_OUT]", 0
    with open('conf.json', 'r+', encoding="utf-8") as f:
        content = f.read()
    conf = json.loads(content)
    API2d_key = conf['API2d_key']
    url = "https://openai.api2d.net/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API2d_key}"
    }
    data = {
        "model": gpt_model,
        "messages": [
            {"role": "system", "content": GodMsg},
            {"role": "user", "content": Msg}],
        "temperature": 0.7,
        "max_tokens": max_tokens
    }
    try:
        response = s.post(url, headers=headers, data=json.dumps(data),verify=False, timeout=max_time)
        js_resp = json.loads(str(response.content, 'utf-8'))
        print(js_resp)
        resp = js_resp["choices"][0]["message"]["content"]
        tmout = 0
    except:
        resp = "抱歉，人家暂时没想好该怎么回答你哦~[TIME_OUT]"
        tmout = 1
    # print("response",response.content)
    return resp, tmout

def getReplyMsgId(msg_chain):
    print("msg_chain", msg_chain)
    sender_id = "Unknown"
    quote_id = 0
    for msg in msg_chain:
        if msg["type"] == "Quote":
            quote_id = int(msg["id"])
            sender_id = str(msg["senderId"])
            # logger.DebugLog('>> 撤回消息 => {} {}'.format(sender_id, quote_id))
            return sender_id, quote_id
    return sender_id, quote_id

def qqReply():
    with open('conf.json', 'r+', encoding="utf-8") as f:
        content = f.read()
    conf = json.loads(content)

    auth_key = conf['auth_key']
    bind_qq = conf['bind_qq']
    sleep_time = conf['sleep_time']
    debug_level = conf['debug_level']
    order_list = conf['order_list']
    super_user_list = conf['super_users']

    receive_groups = conf['receive_groups']
    send_groups = conf['send_groups']
    manage_groups = conf['manage_groups']

    global t2s
    t2s = Text2Speech(conf['speech_key'],conf['service_region'],conf['container_name'],conf['connect_str'],conf['error_url'])

    logger.setDebugLevel(debug_level)

    session = bot.verifySession(auth_key)
    logger.DebugLog(">> session: " + session)
    bot.bindSession(session, bind_qq)
    while True:
        cnt = bot.getMessageCount(session)
        if cnt:
            logger.DebugLog('>> 有消息了 => {}'.format(cnt))
            logger.DebugLog('获取消息内容')
            data = bot.getMsgFromGroup(session)
            # print(type(data[0]))
            print(data[0])
            # ignore private chat and none-chat message
            if 'messageChain' not in data[0]:
                continue
            if data[0]['type'] != 'GroupMessage' and data[0]['type'] != 'FriendMessage':
                continue

            if data[0]['type'] == 'FriendMessage':
                try:
                    sender_friend = str(data[0]['sender']['id'])
                except:
                    sender_friend = ''
                print("Sender friend: {}".format(sender_friend))
                if sender_friend not in super_user_list:
                    continue
                logger.DebugLog('权限用户消息：{}'.format(sender_friend))
                bot.ReplySuperFriend(session, data[0]['messageChain'], sender_friend)
                continue

            ReplyMsgId = data[0]['messageChain'][0]['id']
            print("ReplyMsgId", ReplyMsgId)
            if len(data) == 0:
                logger.DebugLog('消息为空')
                continue
            logger.DebugLog(data)
            logger.DebugLog('解析消息内容')
            At_Bot = bot.checkAtBot(data, bind_qq)
            order, order_task = bot.checkOrder(data)
            # print("AtBot", At_Bot)
            # print("ORDER:",order,order_task)
            msg_chain = copy.deepcopy(data[0]['messageChain'])
            data = bot.parseGroupMsg(data)
            logger.DebugLog(data)
            logger.DebugLog('回复消息内容')
            # if At_Bot == 0:
            #     continue
            if order == 1:
                bot.ReplyOrder(session, data[0], order_task, order_list, msg_chain, int(ReplyMsgId))
            elif At_Bot == 1:
                bot.ReplyMsgToGroup(session, data[0], int(ReplyMsgId))
        # else:
        #	 logger.DebugLog('空闲')
        sleep(sleep_time)
    bot.releaseSession(session, bind_qq)


@app.route('/QQ/send', methods=['GET'])
def qqListenMsg():
    # 类似于Qmsg的功能
    # flask做得接收HTTP请求转为QQ消息
    qq = request.args.get('target', None)
    msg = request.args.get('msg', None)
    bot.sendFriendMessage(bot.session, qq, msg)
    return 'Hello World!'


if __name__ == '__main__':
    s = requests.Session()
    t = threading.Thread(target=qqReply)
    t.setDaemon(True)
    t.start()

    app.run(port='1145', host='127.0.0.1')
