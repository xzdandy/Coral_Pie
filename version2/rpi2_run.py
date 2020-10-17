import argparse
import zmq
import threading

from event_func import *
from trajectoryGraph import TrajectoryGraph
from pubsub import PubSub
from candidatePool import CandidatePool

from coldstart import coldstart

import sys
sys.path.append("..")  # NOQA: E402
from video_storage.video_storage import VideoStorageClient

def arg_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    parser.add_argument("--pubsub")
    parser.add_argument("--video_storage_addr")
    parser.add_argument("--cname")
    parser.add_argument("--dis_thres", nargs='?', default=0.1)
    
    args = parser.parse_args()
    return args


def main():
    import logging.config
    logging.config.fileConfig('logging_config.ini', disable_existing_loggers=False)

    args = arg_parse()

    context = zmq.Context()
    socket = context.socket(zmq.PAIR)
    socket.bind('tcp://*:%s' % args.port)

    # No clean up code
    vstore = VideoStorageClient(args.video_storage_addr, context)
    pubsub = PubSub(args.cname, args.pubsub, context)
    tgraph = TrajectoryGraph()
    vt = VehicleTracking()
    pool = CandidatePool()

    listen_thread = threading.Thread(target=listener_func, args=(pubsub, pool))
    listen_thread.start()

    coldstart(tgraph)

    frame_id = 0
    fps = FPS()
    while True:
        try:
            rawimage, image, bboxes = parse_load(socket)
        except Exception as e:
            logging.warn("Unable to parse: exception %s" % e)
            continue
                
        tracked_bboxes = vt.sort_update(bboxes)
        logging.info("Track result: %s" % tracked_bboxes)
        
        frame_storage(vstore, args.cname, frame_id, rawimage, tracked_bboxes)
        leaving_vehicles = vt.status_update(frame_id, image)

        for vehicle in leaving_vehicles:
            logging.info("Vehicle: %d is leaving" % vehicle.id)
            hist = feature_extraction_adaptive_histogram(vehicle)
            vertexid = vertex_storage(tgraph, args.cname, vehicle)
            messaging(pubsub, vertexid, vehicle.id, hist)

            res = pool.matching(hist, args.dis_thres)
            logging.info("Re-Id for vehicle %d: %s" % (vehicle.id, res))
            edge_storage(tgraph, res, vertexid)


        frame_id += 1
        logging.debug("FPS: %.2f" % fps())

    cleanup()


if __name__ == '__main__':
    main()
