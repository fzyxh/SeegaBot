import json
# import re
import copy
# import requests
from flask import Flask, request
from time import sleep
import threading
import GLOBAL

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

    GLOBAL.logger.setDebugLevel(debug_level)

    session = GLOBAL.bot.verifySession(auth_key)
    GLOBAL.logger.DebugLog(">> session: " + session)
    GLOBAL.bot.bindSession(session, bind_qq)
    while True:
        cnt = GLOBAL.bot.getMessageCount(session)
        if cnt:
            GLOBAL.logger.DebugLog('>> 有消息了 => {}'.format(cnt))
            GLOBAL.logger.DebugLog('获取消息内容')
            data = GLOBAL.bot.getMsgFromGroup(session)
            print("消息内容：")
            # print(type(data))
            print(data)
            for data0 in data:
                if 'messageChain' not in data0:
                    continue
                if data0['type'] != 'GroupMessage' and data0['type'] != 'FriendMessage':
                    continue

                if data0['type'] == 'FriendMessage':
                    try:
                        sender_friend = str(data0['sender']['id'])
                    except:
                        sender_friend = ''
                    # print("Sender friend: {}".format(sender_friend))
                    if sender_friend not in super_user_list:
                        continue
                    # GLOBAL.logger.DebugLog('权限用户消息：{}'.format(sender_friend))
                    GLOBAL.bot.ReplySuperFriend(session, data0['messageChain'], sender_friend)
                    continue

                ReplyMsgId = data0['messageChain'][0]['id']
                print("ReplyMsgId", ReplyMsgId)
                if len(data) == 0:
                    GLOBAL.logger.DebugLog('消息为空')
                    continue
                # GLOBAL.logger.DebugLog(data0)
                GLOBAL.logger.DebugLog('解析消息内容')
                At_Bot = GLOBAL.bot.checkAtBot(data0, bind_qq)
                order, order_task = GLOBAL.bot.checkOrder(data0)
                # print("AtBot", At_Bot)
                # print("ORDER:",order,order_task)
                msg_chain = copy.deepcopy(data0['messageChain'])
                data = GLOBAL.bot.parseGroupMsg(data0)
                GLOBAL.logger.DebugLog(data)
                GLOBAL.logger.DebugLog('回复消息内容')
                # if At_Bot == 0:
                #     continue
                # GLOBAL.logger.DebugLog('data0: {}'.format(data0))
                # GLOBAL.logger.DebugLog('data: {}'.format(data))
                if order == 1:
                    GLOBAL.bot.ReplyOrder(session, data[0], order_task, order_list, msg_chain, int(ReplyMsgId))
                elif At_Bot == 1:
                    GLOBAL.bot.ReplyMsgToGroup(session, data[0], int(ReplyMsgId))
        # else:
        #	 logger.DebugLog('空闲')
        sleep(sleep_time)
    GLOBAL.bot.releaseSession(session, bind_qq)


@GLOBAL.app.route('/QQ/send', methods=['GET'])
def qqListenMsg():
    # 类似于Qmsg的功能
    # flask做得接收HTTP请求转为QQ消息
    qq = request.args.get('target', None)
    msg = request.args.get('msg', None)
    GLOBAL.bot.sendFriendMessage(GLOBAL.bot.session, qq, msg)
    return 'Hello World!'


if __name__ == '__main__':
    t = threading.Thread(target=qqReply)
    t.setDaemon(True)
    t.start()

    GLOBAL.app.run(port=1145, host='127.0.0.1')