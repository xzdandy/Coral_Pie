import zmq
import argparse

from functional_task import *
from trajectoryGraph import TrajectoryGraph
from pubsub import PubSub
from candidatePool import CandidatePool

import sys
sys.path.append("..")  # NOQA: E402
from video_storage.video_storage import VideoStorageClient


def main():
    import logging.config
    logging.config.fileConfig('logging_config.ini', disable_existing_loggers=False)

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', nargs='?', default=5556, help='Port, communication between RPi1 and RPi2')
    parser.add_argument('--pubsub', nargs='?', default='tcp://143.215.207.2:3247', help='PubSub address other camera should subscribe to')
    parser.add_argument("--video_storage_addr", nargs='?', default="tcp://130.207.122.57:1429", help="address of videoStorageServer")
    parser.add_argument('--cname', required=True, help='The name of the camera')
    args = parser.parse_args()

    camera_name = args.cname

    context = zmq.Context()
    socket = context.socket(zmq.PAIR)
    socket.bind('tcp://*:%s' % args.port)

    vstore = VideoStorageClient(args.video_storage_addr, context)
    pubsub = PubSub(args.cname, args.pubsub, context)
    tgraph = TrajectoryGraph()
    pool = CandidatePool()

    listen_thread = threading.Thread(target=listener_func, args=(pubsub, pool))
    listen_thread.start()

    frame_id = 0
    fps = FPS()

    vt = VehicleTracking()
    while True:
        rawimage, image, bboxes = parse_load(socket)
        tracked_bboxes = vt.sort_update(bboxes)
        frame_storage(vstore, camera_name, frame_id, rawimage,
                      tracked_bboxes)
        leaving_vehicles = vt.status_update(frame_id, image)

        for vehicle in leaving_vehicles:
            hist = feature_extraction_adaptive_histogram(vehicle)
            vertexid = vertex_storage(tgraph, camera_name, vehicle)
            messaging(pubsub, vertexid, vehicle.id, hist)

            res = pool.matching(hist, args.dis_thres)
            logging.info("Re-Id for vehicle %d: %s" % (vehicle.id, res))
            edge_storage(tgraph, res, vertexid)

        frame_id += 1
        logging.info('fps: %.2f' % fps())
