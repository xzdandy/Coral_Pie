import requests
import sys
import json
import logging
import time

gtpd_web_gateway = 'http://gtpd-accgw.police.gatech.edu'

HttpUtilLogger = logging.getLogger('HttpUtil')


def getServerId():
    j = requests.get(f'{gtpd_web_gateway}/server').json()

    HttpUtilLogger.debug(json.dumps(j))
    try:
        return j['servers'][0]['id']
    except:
        HttpUtilLogger.critical(j)
        sys.exit(1)


def getSessionId(serverId, username):
    payload = {'addReqList':
               [{
                   'serverId': serverId,
                   'userName': username
               }]}

    j = requests.post(f'{gtpd_web_gateway}/session', data=json.dumps(payload)).json()

    HttpUtilLogger.debug(json.dumps(j))
    try:
        return j['sessionId']
    except:
        HttpUtilLogger.critical(j)
        sys.exit(1)


def login(sessionId, serverId, password):
    payload = {'authReqList':
               [{
                'passwordHash': password,
                'serverId': serverId,
                'authenticationType': 'Clear'
                }]
               }

    j = requests.post(f'{gtpd_web_gateway}/session/{sessionId}', data=json.dumps(payload)).json()

    HttpUtilLogger.debug(json.dumps(j))
    try:
        return ''
    except:
        HttpUtilLogger.critical(j)
        sys.exit(1)


def getStreamGroupId(sessionId):
    payload = {'mode': 'live'}

    j = requests.post(f'{gtpd_web_gateway}/streamGroup?s={sessionId}', data=json.dumps(payload)).json()

    HttpUtilLogger.debug(json.dumps(j))
    try:
        return j['id']
    except:
        HttpUtilLogger.critical(j)
        sys.exit(1)


def getStreamId(sessionId, serverId, streamGroupId, cameraId, targetWidth=1280, targetHeight=960, jpegQuality=8):
    payload = {
        'streamGroupId': streamGroupId,
        'serverId': serverId,
        'cameraId': cameraId,
        'params': {
            'targetWidth': targetWidth,
            'targetHeight': targetHeight,
            'jpegQuality': jpegQuality
        }
    }

    j = requests.post(f'{gtpd_web_gateway}/stream?s={sessionId}', data=json.dumps(payload)).json()

    HttpUtilLogger.debug(json.dumps(j))
    try:
        return j['id']  # and blablabla
    except:
        HttpUtilLogger.critical(j)
        sys.exit(-1)


def getFrame(sessionId, streamId, frame, to=10, retries=100):
    tries = 0

    start_time = time.time()
    while True:
        r = requests.get(f'{gtpd_web_gateway}/stream/{streamId}/image?to={to}&r={frame + tries}&s={sessionId}')

        tries = tries + 1

        if r.status_code == 200:
            end_time = time.time()
            HttpUtilLogger.debug(f'StreamId: {streamId}, Frames: {frame + tries - 1}, Content: Recevied, Time: {end_time-start_time:.3f} secs')
            return (r.content, frame + tries)

        if tries >= retries:
            HttpUtilLogger.debug(f'StreamId: {streamId}, Frames: {frame + tries - 1}, Content: None')
            return (None, frame + tries)


def disconnectStream(sessionId, streamId):
    requests.delete(f'{gtpd_web_gateway}/stream/{streamId}?s={sessionId}')


def disconnectStreamGroup(sessionId, streamGroupId):
    requests.delete(f'{gtpd_web_gateway}/streamGroup/{streamGroupId}?s={sessionId}')


if __name__ == '__main__':
    import logging.config
    logging.config.fileConfig('logging_config.ini')

    with open('./Config/user.json') as f:
        userconfig = json.load(f)

    with open('./Config/cameras.json') as f:
        cameraconfig = json.load(f)

    serverId = getServerId()
    sessionId = getSessionId(serverId, userconfig['username'])

    login(sessionId, serverId, userconfig['password'])
    streamGroupId = getStreamGroupId(sessionId)

    streamId = getStreamId(sessionId, serverId, streamGroupId, cameraconfig['ferst_crc']['cameraId'])

    getFrame(sessionId, streamId, 0)

    disconnectStream(sessionId, streamId)
    disconnectStreamGroup(sessionId, streamGroupId)
