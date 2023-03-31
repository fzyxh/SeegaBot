import re
import json
from io import BytesIO
from PIL import Image
import urllib.request
import requests
import GLOBAL

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
        GLOBAL.logger.DebugLog(res)
        if res['code'] == 0:
            return res['session']
        return None

    def bindSession(self, session, qq):
        """校验并激活Session，同时将Session与一个已登录的Bot绑定"""
        data = {"sessionKey": session, "qq": qq}
        url = self.addr + 'bind'
        res = requests.post(url, data=json.dumps(data)).json()
        GLOBAL.logger.DebugLog(res)
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
        GLOBAL.logger.DebugLog(res)
        if res['code'] == 0:
            return True
        return False

    def getMsgFromGroup(self, session):
        url = self.addr + 'fetchLatestMessage?count=10&sessionKey=' + session
        res = requests.get(url).json()
        if res['code'] == 0:
            return res['data']
        return None

    def parseGroupMsg(self, item):
        res = []
        if item is None:
            return res
        if item['type'] == 'GroupMessage':
            type = item['messageChain'][-1]['type']
            if type == 'Image':
                text = item['messageChain'][-1]['url']
            elif type == 'Plain':
                text = item['messageChain'][-1]['text']
            elif type == 'Face':
                text = item['messageChain'][-1]['faceId']
            else:
                text = ''
                GLOBAL.logger.TraceLog(">> 当前消息类型暂不支持：=> " + type)
            name = item['sender']['memberName']
            group_id = str(item['sender']['group']['id'])
            group_name = item['sender']['group']['name']
            res.append({'text': text, 'type': type, 'name': name, 'groupId': group_id, 'groupName': group_name})
        return res

    def checkAtBot(self, item, BotQQ):
        if item is None:
            return 0
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

    def checkOrder(self, item):
        pattern = r'^[ ]*\/[0-9a-zA-Z_]+'
        if item is None:
            return 0, ''
        if item['type'] == 'GroupMessage':
            for item2 in item['messageChain']:
                type = item2['type']
                if type == 'Plain':
                    matches = re.findall(pattern,item2['text'],re.MULTILINE)
                    # print("Order matches", matches)
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

        GLOBAL.logger.DebugLog(">> 消息类型：" + type)
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
            GLOBAL.logger.TraceLog(">> 当前消息类型暂不支持回复：=> " + type)
            return 0
        data = {
            "sessionKey": session,
            "group": group_id,
            'quote': ReplyMsgId,
            "messageChain": message
        }
        GLOBAL.logger.DebugLog(">> 消息内容：" + str(data))
        url = self.addr + 'sendGroupMessage'
        try:
            res = requests.post(url, data=json.dumps(data)).json()
        except:
            GLOBAL.logger.DebugLog(">> 回复失败")
            return 0
        GLOBAL.logger.DebugLog(">> 请求返回：" + str(res))
        if res['code'] == 0:
            return res['messageId']
        return 0

    def revokeMsgGroup(self, session, target, msgId):
        data = {
            "sessionKey": session,
            "target": target,
            'messageId': msgId
        }
        GLOBAL.logger.DebugLog(">> 撤回消息：" + str(msgId))
        url = self.addr + 'recall'
        try:
            res = requests.post(url, data=json.dumps(data)).json()
        except:
            GLOBAL.logger.DebugLog(">> 撤回失败")
            return 0
        GLOBAL.logger.DebugLog(">> 请求返回：" + str(res))
        if res['code'] == 0:
            return res['msg']

    def muteMemberGroup(self, session, target, memberId, mute_time=86400):
        data = {
            "sessionKey": session,
            "target": target,
            "memberId": memberId,
            'time': mute_time
        }
        GLOBAL.logger.DebugLog(">> 禁言成员：" + str(memberId))
        url = self.addr + 'mute'
        try:
            res = requests.post(url, data=json.dumps(data)).json()
        except:
            GLOBAL.logger.DebugLog(">> 禁言失败")
            return 0
        GLOBAL.logger.DebugLog(">> 请求返回：" + str(res))
        if res['code'] == 0:
            return res['msg']

    def ReplyOrder(self, session, msg, order, order_list, msg_chain, ReplyMsgId):
        print("ReplyOrder")
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
            if order != "editimg": # special check TODO:Debug here
                return 0
        if order not in order_list:
            content = "Your order is not in the order list. Enter /h to get more information."
        else:
            if order == "h":
                content = "◆ Order List:\n" + "\n".join(str(i) for i in order_list)
                content = content + "\nTo get order details, please enter /h ORDER."
            elif order == "whoami":
                content = "I'm a bot Powered by Mirai-Core, and my author is Phinney.\n" + "To get more information, please visit https://github.com/fzyxh/SeegaBot."
            elif order == "revoke":
                revoke_name, quote_id = getReplyMsgId(msg_chain)
                GLOBAL.bot.revokeMsgGroup(session, group_id, quote_id)
                content = name + "认为" + revoke_name + "发送了不当内容，已予以撤回。如有疑问请联系管理员处理。"
            elif order == "kick":
                kick_name, quote_id = getReplyMsgId(msg_chain)
                GLOBAL.bot.revokeMsgGroup(session, group_id, quote_id)
                GLOBAL.bot.muteMemberGroup(session, int(group_id), int(kick_name))
                content = name + "认为" + kick_name + "发送了不当内容，已予以撤回并禁言。如有疑问请联系管理员处理。"
            elif order == "speak":
                try:
                    question_text = text.split('/speak', 1)[1]
                    voice_text, tmout = getGPTMsg("你是一个可爱的猫娘，你会傲娇地回答问题：", question_text)
                except:
                    voice_text = ""
                    tmout = 1
                if tmout == 1:
                    voice_text = ""
                GLOBAL.t2s.getVoice(voice_text)
                voice_url = GLOBAL.t2s.upload()
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
                GLOBAL.t2s.getVoice(voice_text)
                voice_url = GLOBAL.t2s.upload()
            elif order == "gpt4":
                try:
                    question_text = text.split('/gpt4', 1)[1]
                    content, tmout = getGPTMsg("你是一个可爱的猫娘，你会傲娇地回答问题：", question_text, "gpt-4-0314", 2000, 60)
                except:
                    content = "抱歉，人家暂时没想好该怎么回答你哦~[EXCEPTION_HANDLING_GPT4]"
                    tmout = 1
            elif order == "gptmodel":
                try:
                    text2 = text.split('/gptmodel', 1)[1]
                    print("text2:{}".format(text2))
                    question_text = text2.split(' ',2)
                    # print(question_text)
                    content, tmout = getGPTMsg("你是一个可爱的猫娘，你会傲娇地回答问题：", question_text[2], question_text[1], 2000, 60)
                except:
                    content = "抱歉，人家暂时没想好该怎么回答你哦~[EXCEPTION_HANDLING_GPTMODEL]"
                    tmout = 1
            elif order == "createimg":
                try:
                    question_text = text.split('/createimg', 1)[1]
                    # print(question_text)
                    content_url, tmout = getGPTImg(question_text, 60)
                except:
                    content_url = "抱歉，人家暂时没想好该怎么回答你哦~[EXCEPTION_HANDLING_DALLE]"
                    tmout = 1
            elif order == "editimg":
                try:
                    type = "Plain"
                    # question_text = text.split('/editimg', 1)[1]
                    question_text, img_raw_url = getImgUrl(msg_chain)
                    question_text = question_text.split('/editimg', 1)[1]
                    print(question_text, img_raw_url)
                    # print(question_text)
                    content_url, tmout = getGPTEditImg(question_text, img_raw_url, 60)
                except:
                    content_url = "抱歉，人家暂时没想好该怎么回答你哦~[EXCEPTION_HANDLING_DALLE_EDIT]"
                    tmout = 1
            else:
                content = "Unknown Error."
                GLOBAL.logger.DebugLog(">> 当前命令类型暂不支持回复：=> " + order)

        # if type == 'Plain':
        #     response = getGPTMsg("你是一个可爱的猫娘，你会傲娇地回答问题：", text)
        #     content = response["choices"][0]["message"]["content"]

        GLOBAL.logger.DebugLog(">> 消息类型：" + type)
        if type == 'Plain':
            # message = [{"type": type, "text": content1 + '\n' + content3}]
            message = [{"type": type, "text": content}]
        else:
            GLOBAL.logger.TraceLog(">> 当前消息类型暂不支持回复：=> " + type)
            return 0
        # important!!!
        if order == 'speak' or order == 'repeat':
            message = [{"type": "Voice", "url": voice_url}]
        if (order == 'createimg' or order == 'editimg') and tmout == 0:
            message= [{"type": "Image", "url": content_url}]
        data = {
            "sessionKey": session,
            "group": group_id,
            'quote': ReplyMsgId,
            "messageChain": message
        }
        GLOBAL.logger.DebugLog(">> 消息内容：" + str(data))
        url = self.addr + 'sendGroupMessage'
        try:
            res = requests.post(url, data=json.dumps(data)).json()
        except:
            GLOBAL.logger.DebugLog(">> 回复失败")
            return 0
        GLOBAL.logger.DebugLog(">> 请求返回：" + str(res))
        if res['code'] == 0:
            return res['messageId']
        return 0

    def ReplySuperFriend(self, session, msg_chain, qq):
        text = ""
        for msg in msg_chain:
            if msg['type'] == 'Plain':
                text = msg['text']
        GLOBAL.logger.DebugLog("Super User: {}".format(text))
        reply_msg, tmout = getGPTMsg("你是一个尽心尽力为主人排忧解难的优秀助手", text, "gpt-4", 2000, 120)
        if tmout == 1:
            reply_msg = "抱歉，接口响应有些久哦~请等一会再试试吧！[TIME_OUT]"
        GLOBAL.logger.DebugLog("GPT Reply: {}".format(reply_msg))
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
            GLOBAL.logger.DebugLog(">> 发送失败")
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
            GLOBAL.logger.DebugLog(">> 发送失败")
            return 0
        if res['code'] == 0:
            return res['messageId']
        return 0


# logger = Logger()

# app = Flask(__name__)

# reference: https://platform.openai.com/docs/models
def getGPTMsg(GodMsg="", Msg="", gpt_model="gpt-3.5-turbo", max_tokens=3000, max_time=40):
    if Msg == "":
        return "抱歉，人家暂时没想好该怎么回答你哦~[TIME_OUT]", 1
    with open('conf.json', 'r+', encoding="utf-8") as f:
        content = f.read()
    conf = json.loads(content)
    # API2d_key = conf['API2d_key']
    # url = "https://openai.api2d.net/v1/chat/completions" # openai api is limited in China Mainland
    domain = conf['openai_domain']
    API2d_key = conf['openai_key']
    url = "https://" + domain + "/v1/chat/completions"
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
        response = GLOBAL.s.post(url, headers=headers, data=json.dumps(data),verify=False, timeout=max_time)
        js_resp = json.loads(str(response.content, 'utf-8'))
        print(js_resp)
        resp = js_resp["choices"][0]["message"]["content"]
        tmout = 0
    except:
        resp = "抱歉，人家暂时没想好该怎么回答你哦~[TIME_OUT]"
        tmout = 1
    # print("response",response.content)
    return resp, tmout

# reference: https://platform.openai.com/docs/guides/images/usage?lang=curl
def getGPTImg(Msg="", max_time=30):
    if Msg == "":
        return "抱歉，人家暂时没想好该怎么回答你哦~[TIME_OUT]", 1
    with open('conf.json', 'r+', encoding="utf-8") as f:
        content = f.read()
    conf = json.loads(content)
    # API2d_key = conf['API2d_key']
    # url = "https://openai.api2d.net/v1/chat/completions" # openai api is limited in China Mainland
    domain = conf['openai_domain']
    API2d_key = conf['openai_key']
    url = "https://"+ domain + "/v1/images/generations"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API2d_key}"
    }
    data = {
        "prompt": Msg,
        "n": 1, # how many img do you want once
        "size": "1024x1024",
        "response_format": "url"
    }
    try:
        response = GLOBAL.s.post(url, headers=headers, data=json.dumps(data),verify=False, timeout=max_time)
        js_resp = json.loads(str(response.content, 'utf-8'))
        print(js_resp)
        resp = js_resp["data"][0]["url"]
        # print("IMG url: {}".format(resp))
        tmout = 0
    except:
        resp = "抱歉，人家暂时没想好该怎么回答你哦~[TIME_OUT]"
        tmout = 1
    # print("response",response.content)
    return resp, tmout
# reference: https://platform.openai.com/docs/guides/images/usage?lang=curl
def getGPTEditImg(Msg="", ImgUrl="", max_time=30):
    if Msg == "" or ImgUrl == "":
        return "抱歉，人家暂时没想好该怎么回答你哦~[TIME_OUT]", 1
    urllib.request.urlretrieve(ImgUrl, "Img2Edit.png")
    img = Image.open("Img2Edit.png")
    img = img.convert('RGBA')
    width, height = 1024, 1024
    img = img.resize((width, height))
    # Convert the image to a BytesIO object
    img.save("ImgResize.png", format='PNG')

    with open('conf.json', 'r+', encoding="utf-8") as f:
        content = f.read()
    conf = json.loads(content)
    # API2d_key = conf['API2d_key']
    # url = "https://openai.api2d.net/v1/chat/completions" # openai api is limited in China Mainland
    domain = conf['openai_domain']
    API2d_key = conf['openai_key']
    url = "https://"+ domain + "/v1/images/edits"
    headers = {
        # "Content-Type": "multipart/form-data",
        "Authorization": f"Bearer {API2d_key}"
    }
    file = {
        "image": ("ImgResize.png", open("ImgResize.png","rb"), 'image/png', {}),
        # "mask": ("jbmask.png", open("jbmask2.png", "rb"), 'image/png', {})
    }
    data = {
        "prompt": Msg,
        "n": 1, # how many img do you want once
        "size": "1024x1024",
        "response_format": "url"
    }
    # print("EditImg3")
    try:
        response = GLOBAL.s.post(url, headers=headers, files=file, data=data, verify=False, timeout=max_time)
        js_resp = json.loads(str(response.content, 'utf-8'))
        print(js_resp)
        resp = js_resp["data"][0]["url"]
        # print("IMG url: {}".format(resp))
        tmout = 0
    except:
        print("ERROR on EditImg")
        resp = "抱歉，人家暂时没想好该怎么回答你哦~[TIME_OUT]"
        tmout = 1
    # print("response",response.content)
    return resp, tmout

def getReplyMsgId(msg_chain):
    # print("msg_chain", msg_chain)
    sender_id = "Unknown"
    quote_id = 0
    for msg in msg_chain:
        if msg["type"] == "Quote":
            quote_id = int(msg["id"])
            sender_id = str(msg["senderId"])
            # logger.DebugLog('>> 撤回消息 => {} {}'.format(sender_id, quote_id))
            return sender_id, quote_id
    return sender_id, quote_id

def getImgUrl(msg_chain):
    # print("img_url: msg_chain", msg_chain)
    img_url = ""
    text = ""
    for msg in msg_chain:
        if msg["type"] == "Image":
            img_url = msg["url"]
        if msg["type"] == "Plain":
            text += msg["text"]
    return text, img_url