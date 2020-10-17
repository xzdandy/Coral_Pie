from HttpUtil import *
from streamUtil import *

import logging
import os
import sys
import time
import io
import zmq
import threading
import numpy as np

from queue import Queue
from PIL import Image
from edgetpu.basic.basic_engine import BasicEngine

import sys
sys.path.append("..")  # NOQA: E402
from archive.object_detection import FPS, ReadLabelFile


SDLogger = logging.getLogger('Streaming')

Labels = ReadLabelFile('/home/pi/edgetpu_api/examples/coral_guide/coco_labels.txt')
MODELPATH = '/home/pi/edgetpu_api/examples/coral_guide/mobilenet_ssd_v2_coco_quant_postprocess_edgetpu.tflite'

input_w, input_h, tensor_start_index = edgeTpuModelInfo(MODELPATH)

threshold = 0.2
target_labels = [2]
top_k = 5

jobQueue = Queue()
resizeQueue = Queue()


def resizeTask(inqueue, outQueue):
    fps = FPS()
    while True:
        obj = inqueue.get()
        if obj is None:
            outQueue.put(None)
            break

        img = Image.open(io.BytesIO(obj))
        # We resize the image, the other choice is keep_aspect_ratio
        img = img.resize((input_w, input_h), Image.NEAREST)  # this step is slow sadly, maybe another thread?

        outQueue.put((img, obj))
        SDLogger.info(f'Resize FPS: {fps():.2f}')


def coralQueue(inqueue, addr):
    context = zmq.Context()
    socket = context.socket(zmq.PAIR)
    socket.connect('tcp://%s' % addr)

    engine = BasicEngine(MODELPATH)

    fps = FPS()

    while True:
        obj = inqueue.get()
        if obj is None:
            socket.send_pyobj(None)  # BLOCK HERE
            break

#        start_time = time.time()
        img, content = obj

        input_tensor = np.asarray(img).flatten()
        _, raw_result = engine.RunInference(input_tensor)
        bbox_result = []
        num_candidates = raw_result[tensor_start_index[3]]
        for i in range(int(round(num_candidates))):
            score = raw_result[tensor_start_index[2] + i]
            if score > threshold:
                label_id = int(round(raw_result[tensor_start_index[1] + i]))
                if label_id in target_labels:
                    y1 = max(0.0, raw_result[tensor_start_index[0] + 4 * i])
                    x1 = max(0.0, raw_result[tensor_start_index[0] + 4 * i + 1])
                    y2 = min(1.0, raw_result[tensor_start_index[0] + 4 * i + 2])
                    x2 = min(1.0, raw_result[tensor_start_index[0] + 4 * i + 3])

                    # This is ratio.
                    bbox_result.append([x1, y1, x2, y2, score])
        bbox_result.sort(key=lambda x: -x[4])

#        end_time = time.time()
#        SDLogger.debug(f'Preprocess + Inference costs: {end_time-start_time:.3f}')

        try:
            pass
            socket.send_pyobj((content, bbox_result[:top_k]), flags=zmq.NOBLOCK)
        except Exception as e:
            SDLogger.error('Error when sending the detection result: %s' % e)
        SDLogger.info(f'Detection FPS: {fps():.2f}')


def streamcore(sessionId, streamId, num):
    frame = 0
    success = 0
    fps = FPS()

    for i in range(num):
        (content, frame) = getFrame(sessionId, streamId, frame)

        if content is None:
            SDLogger.warning(f'Missing {i}th frame')
            continue

        success = success + 1

        try:
            resizeQueue.put(content)
            SDLogger.debug(f'Load FPS: {fps():.2f}')
        except Exception as e:
            SDLogger.error(f'Error when processing: {e}')

    SDLogger.info(f'Success ratio: {success}_of_{num}')


def streaming(auth, cameraconfig, cname, num):
    try:
        cameraId = cameraconfig[cname]['cameraId']
    except Exception as e:
        SDLogger.error(f'Fail to get cameraId for {cname}: {e}')
        return
    streamId = getStreamId(auth['sessionId'], auth['serverId'], auth['streamGroupId'], cameraId)
    SDLogger.info(f'Successfully acquire the streamId {streamId} for camera {cname}')

    streamcore(auth['sessionId'], streamId, num)

    disconnectStream(auth['sessionId'], streamId)
    disconnectStreamGroup(auth['sessionId'], auth['streamGroupId'])


if __name__ == '__main__':
    import logging.config
    logging.config.fileConfig('logging_config.ini', disable_existing_loggers=False)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger('HttpUtil').setLevel(logging.INFO)

    args = arghelp()

    userconfig, cameraconfig = readConfig()
    auth = commonLogin(userconfig)
    SDLogger.info(f'Successfully login into GTPD live camera gateway: {auth}')

    coralpip = threading.Thread(target=coralQueue, args=(jobQueue, '%s:%s' % (args.host, args.port)))
    coralpip.deamon = True
    coralpip.start()

    resizepip = threading.Thread(target=resizeTask, args=(resizeQueue, jobQueue))
    resizepip.deamon = True
    resizepip.start()

    streaming(auth, cameraconfig, args.cname, args.num)

    resizeQueue.put(None)
    SDLogger.info(f'Remaining resize jobs: {resizeQueue.qsize()}')
    resizepip.join()
    SDLogger.info(f'Remaining detection jobs: {jobQueue.qsize()}')
    coralpip.join()
