import zmq
import argparse
import logging
import os
import shutil
import time
import numpy
import io
import json
import cv2
import threading
import queue

from PIL import Image
from PIL import ImageDraw
from sort.sort import *

import sys
sys.path.append("..")  # NOQA: E402
from archive.object_detection import FPS

from trajectoryGraph import TrajectoryGraph
from pubsub import PubSub
from adaptive_hist import generate_hist_from_bbox, bhattacharyya

logging.getLogger('PIL').setLevel(logging.WARNING)  # Disable the debug logging from PIL
SLogger = logging.getLogger('Server')

context = zmq.Context()


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)


def createEmptyDir(dir):
    try:
        os.makedirs(dir)
    except FileExistsError:
        SLogger.warning(f'Emtpy the existing directory {dir}')
        shutil.rmtree(dir)
        os.makedirs(dir)


def listen(port, out_dir, pubsub, tgraph, matching_queue):
    socket = context.socket(zmq.PAIR)
    socket.bind('tcp://*:%s' % port)

    index = 0
    colorNames = ['aqua', 'black', 'blue', 'fuchsia',
                  'gray', 'green', 'lime', 'maroon',
                  'navy', 'olive', 'purple', 'red',
                  'silver', 'teal', 'white', 'yellow']
    colorptr = 0
    idColorMap = {}
    idCountMap = {}
    HOT_INIT = 5
    MIN_GAP = 0

    fps = FPS()
    mot_tracker = Sort()

    SLogger.info('Start listening on %s' % port)
    while True:
        obj = socket.recv_pyobj()

        if obj is None:
            break
        try:
            bimageobject, bbox = obj
            image = Image.open(io.BytesIO(bimageobject))  # for live camera stream use the raw from http
            # image = Image.frombytes(*bimageobject) # for recorded live camera stream use image.tobytes()?
        except Exception as e:
            SLogger.error('Unable to parse the recevied object. Error: %s' % e)
            continue

        # convert ratio to actual coordinates
        w, h = image.size
        for i in range(len(bbox)):
            bbox[i][0] = bbox[i][0] * w  # x1
            bbox[i][1] = bbox[i][1] * h  # y1
            bbox[i][2] = bbox[i][2] * w  # x2
            bbox[i][3] = bbox[i][3] * h  # y2

        trackers = mot_tracker.update(numpy.asarray(bbox))

        SLogger.debug('Track result: %s' % trackers)

        track_time = time.time()
        # Draw the bounding box and write to disk !!! SLOW OPERATION !!!
        draw = ImageDraw.Draw(image)
        for t in trackers:
            if t[4] not in idColorMap:
                idColorMap[t[4]] = colorNames[colorptr]
                colorptr = (colorptr + 1) % len(colorNames)
            draw.rectangle(t[0:4].tolist(), outline=idColorMap[t[4]])
            draw.text(t[0:2].tolist(), str(t[4]), fill='red')
        filename = os.path.join(out_dir, '%d.jpeg' % index)
        image.save(filename, 'JPEG')

        draw_time = time.time()
        SLogger.debug('Successfully save %s, Draw Time: %.3f' % (filename, (draw_time - track_time)))

        # Maintain the identity of the vehicle
        for t in trackers:
            if t[4] not in idCountMap:
                idCountMap[t[4]] = {'first': index, 'bbox': []}
            idCountMap[t[4]]['last'] = index
            idCountMap[t[4]]['hot'] = HOT_INIT
            # TODO We need to fill in empty bbox in case of short-term missing tracking
            idCountMap[t[4]]['bbox'].append(t[0:4])

        leavingIds = []
        for key in idCountMap:
            idCountMap[key]['hot'] -= 1
            if idCountMap[key]['hot'] <= 0:
                leavingIds.append(key)

        for key in leavingIds:
            if idCountMap[key]['last'] - idCountMap[key]['first'] > MIN_GAP:
                SLogger.info('Vehicle %s leaving: [%s, %s]' % (key, idCountMap[key]['first'], idCountMap[key]['last']))
                try:
                    vertexid = tgraph.addDetection('veh%d' % int(key), pubsub.cname, time.time(), '%s-%s' % (idCountMap[key]['first'], idCountMap[key]['last']))
                    SLogger.debug('Successfully create detection vertex %s in graph' % vertexid)
                except Exception as e:
                    SLogger.error('Fail to create the detection vertex: %s' % e)
                    continue

                # TODO Pick a frame
                target_index = idCountMap[key]['first']
                target_bbox = idCountMap[key]['bbox'][target_index - idCountMap[key]['first']]
                target_image = cv2.imread(os.path.join(out_dir, '%d.jpeg' % target_index))
                ahist = generate_hist_from_bbox(target_image, target_bbox)

                event = {'vertexid': vertexid,
                         'selfid': key,
                         'camera': pubsub.cname,
                         'timestamp': time.time(),
                         'hist': ahist}
                matching_queue.put(event)
                json_event = json.dumps(event, cls=NumpyEncoder)

                try:
                    pubsub.publishMessage(json_event)
                    SLogger.debug('Publish event %s' % json_event)
                except Exception as e:
                    SLogger.error('Fail to publish event %s' % json_event)
            else:
                SLogger.warning('Vehicle %s is ignored due to the short track: [%s, %s]' % (key, idCountMap[key]['first'], idCountMap[key]['last']))
            del idCountMap[key]

        index += 1
        SLogger.debug('FPS: %.2f' % fps())

    # Better debug output
    rv = [(key, idCountMap[key]['first'], idCountMap[key]['last'], idCountMap[key]['hot']) for key in idCountMap]
    SLogger.debug('Remained vehicles: %s' % rv)


def listen_candidates(pubsub, cand):
    while True:
        topic, message_data = pubsub.receiveData()
        SLogger.debug('Recevied event %s-%s' % (topic, message_data))
        cand.append(json.loads(message_data))


def matching(queue, cand, tgraph):
    mthreshold = 0.1
    while True:
        target_vehicle = queue.get()
        target_hist = target_vehicle['hist']
        conf = -1
        for i in range(len(cand)):
            c_hist = np.asarray(cand[i]['hist'])
            conf = bhattacharyya(target_hist, c_hist)
            if conf >= mthreshold:
                break

        if conf < mthreshold:
            SLogger.warning('target vehicle (%s-%s) is not matched' % (target_vehicle['vertexid'], target_vehicle['selfid']))
        else:
            res = cand.pop(i)
            SLogger.info('target vehicle (%s-%s) is matched with (%s-%s) from camera %s' %
                         (target_vehicle['vertexid'], target_vehicle['selfid'], res['vertexid'], res['selfid'], res['camera']))
            tgraph.linkDetection(res['vertexid'], target_vehicle['vertexid'], conf)


def main():
    import logging.config
    logging.config.fileConfig('logging_config.ini', disable_existing_loggers=False)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--port', nargs='?', type=int, default=5556,
        help='Port the server should listen on')
    parser.add_argument(
        '--pubsub', nargs='?', type=str, default='tcp://143.215.207.2:3247',
        help='PubSub address other camera should subscribe to')
    parser.add_argument(
        '--storage', nargs='?', type=str, default='output',
        help='Directory to store the video')
    parser.add_argument(
        '--cname', nargs='?', type=str, default='ferst_state',
        help='The name of the camera')
    args = parser.parse_args()

    try:
        createEmptyDir(args.storage)
    except Exception as e:
        SLogger.fatal('Unable to create the output directory: %s' % e)
        sys.exit(-1)

    pubsub = PubSub(args.cname, args.pubsub, context)
    SLogger.info('Successfully start pubsub service')

    tgraph = TrajectoryGraph()
    SLogger.info('Successfully connect to graph database')

    time.sleep(5)

    cand = []
    sub_thread = threading.Thread(target=listen_candidates, args=(pubsub, cand))
    sub_thread.start()

    matching_queue = queue.SimpleQueue()
    match_thread = threading.Thread(target=matching, args=(matching_queue, cand, tgraph))
    match_thread.start()

    listen(args.port, args.storage, pubsub, tgraph, matching_queue)


if __name__ == '__main__':
    main()
