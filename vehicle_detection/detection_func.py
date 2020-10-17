import io
import json
import logging
import time
import collections
import numpy as np
import zmq

from PIL import Image
from HttpUtil import *

DFLogger = logging.getLogger("Detection_Func")


class FPS:
    def __init__(self, avarageof=50):
        self.frametimestamps = collections.deque(maxlen=avarageof)

    def __call__(self):
        self.frametimestamps.append(time.time())
        if(len(self.frametimestamps) > 1):
            return len(self.frametimestamps)/(self.frametimestamps[-1]-self.frametimestamps[0])
        else:
            return 0.0


def timing(f):
    def _decorator(*args, **kwargs):
        time1 = time.time()
        ret = f(*args, **kwargs)
        time2 = time.time()
        DFLogger.debug("%s function took %.3f ms" % (f.__name__, (time2 - time1) * 1000.0))
        return ret
    return _decorator


class ImageSequenceStream:
    def __init__(self, seqpath, max_fails=5):
        self.seqpath = seqpath
        self.max_fails = max_fails
        self.frameId = 0

    @timing
    def fetch_frame(self):
        fails = 0
        while True:
            path = self.seqpath % self.frameId
            try:
                with open(path, "rb") as f:
                    frame = f.read()
            except:
                fails += 1
                self.frameId += 1
                if fails == self.max_fails:
                    raise
            else:
                self.frameId += 1
                return frame


class SingleCampusCameraStream:
    def __init__(self, camera_name,
                 user_config_path,
                 cameras_config_path):
        self.camera_name = camera_name
        self.user_config_path = user_config_path
        self.cameras_config_path = cameras_config_path

    def login(self):
        with open(self.user_config_path) as f:
            userconfig = json.load(f)
        with open(self.cameras_config_path) as f:
            cameraconfig = json.load(f)

        self.cameraId = cameraconfig[self.camera_name]["cameraId"]

        self.serverId = getServerId()
        self.sessionId = getSessionId(self.serverId, userconfig['username'])
        login(self.sessionId, self.serverId, userconfig["password"])
        self.streamGroupId = getStreamGroupId(self.sessionId)

        self.streamId = getStreamId(self.sessionId, self.serverId, self.streamGroupId, self.cameraId)
        self.frame_num = 0

    @timing
    def fetch_frame(self):
        (bytearr, self.frame_num) = getFrame(self.sessionId, self.streamId, self.frame_num)
        return bytearr

    def logout(self):
        disconnectStream(self.sessionId, self.streamId)
        disconnectStreamGroup(self.sessionId, self.streamGroupId)


@timing
def load_frame(bytearr):
    image = Image.open(io.BytesIO(bytearr))
    # Explicitly load the image
    image.load()
    return image


@timing
def resize_frame(image, w, h):
    return image.resize((w, h), Image.NEAREST)


@timing
def inference(engine, image):
    input_tensor = np.asarray(image).flatten()
    _, raw_result = engine.RunInference(input_tensor)
    return raw_result


@timing
def post_inference(raw_result, tensor_start_index, target_labelIds, threshold, top_k, w, h):
    bbox_result = []
    num_candidates = raw_result[tensor_start_index[3]]
    for i in range(int(round(num_candidates))):
        score = raw_result[tensor_start_index[2] + i]
        if score > threshold:
            label_id = int(round(raw_result[tensor_start_index[1] + i]))
            if label_id in target_labelIds:
                y1 = max(0.0, raw_result[tensor_start_index[0] + 4 * i])
                x1 = max(0.0, raw_result[tensor_start_index[0] + 4 * i + 1])
                y2 = min(1.0, raw_result[tensor_start_index[0] + 4 * i + 2])
                x2 = min(1.0, raw_result[tensor_start_index[0] + 4 * i + 3])

                bbox_result.append([x1 * w, y1 * h, x2 * w, y2 * h, score])
    bbox_result.sort(key=lambda x: -x[4])
    return bbox_result[:top_k]


@timing
def send_detection_results(socket, image, bboxes):
    if socket is not None:
        socket.send_pyobj((image, bboxes), flags=zmq.NOBLOCK)


# Below are utility functions

def get_target_labelIds(labelpath, target_labels=["car", "bus", "truck"]):
    with open(labelpath, 'r', encoding="utf-8") as f:
        lines = f.readlines()
    ret = {}
    for line in lines:
        pair = line.strip().split(maxsplit=1)
        labelname = pair[1].strip()
        if labelname in target_labels:
            ret[int(pair[0])] = labelname
    return ret


def engine_info(engine):
    output_tensors_sizes = engine.get_all_output_tensors_sizes()
    tensor_start_index = [0]
    offset = 0
    for i in range(3):
        offset = offset + output_tensors_sizes[i]
        tensor_start_index.append(offset)

    _, height, width, _ = engine.get_input_tensor_shape()

    return (width, height, tensor_start_index)
