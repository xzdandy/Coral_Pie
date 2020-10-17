import logging.config
import cv2
import numpy
import io
import argparse
import logging
from PIL import Image

from edgetpu.detection.engine import DetectionEngine
#from sort.sort import *
from sort2.sort import *

import sys
sys.path.append("..")  # NOQA: E402
from video_storage.video_storage import VideoStorageClient

# BGR format
COLORBGR = [(0, 0, 255), (0, 165, 255), (0, 255, 255), (0, 255, 0),
            (255, 0, 0), (130, 0, 75), (238, 130, 238), (0, 0, 0),
            (127, 127, 127), (255, 255, 255)]

logging.getLogger('PIL').setLevel(logging.WARNING)  # Disable the debug logging from PIL
logger = logging.getLogger('DT')

logging.config.fileConfig('logging_config.ini', disable_existing_loggers=False)


# Function to read labels from text files.
def ReadLabelFile(file_path):
    with open(file_path, 'r', encoding="utf-8") as f:
        lines = f.readlines()
    ret = {}
    for line in lines:
        pair = line.strip().split(maxsplit=1)
        ret[int(pair[0])] = pair[1].strip()
    return ret


def count_target_bbox(ans, labels, target_labels):
    count = 0
    for obj in ans:
        if labels[obj.label_id] in target_labels:
            count += 1
    return count


def generate_sort_tracker_bbox(ans, labels, target_labels):
    bboxs = []
    for obj in ans:
        if labels[obj.label_id] in target_labels:
            bbox = obj.bounding_box.flatten().tolist()
            bbox.append(obj.score)
            bboxs.append(bbox)
    return bboxs


def draw_trackers(frame, trackers):
    for t in trackers:
        x1, y1, x2, y2, vid = t.tolist()
        color = COLORBGR[int(vid) % len(COLORBGR)]
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
        cv2.putText(frame, str(vid), (int(x1), int(y1)-15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2)
    return frame


def draw_bboxs(frame, bboxs):
    for t in bboxs:
        x1, y1, x2, y2, vid = t
        color = COLORBGR[0]
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
       # cv2.putText(frame, str(vid), (int(x1), int(y1)-15),
       # cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2)
    return frame


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--video", required=True, help="path to the input video file")
    ap.add_argument("-n", "--name", required=True, help="camera name")
    ap.add_argument("-m", "--model", nargs='?',
                    default="/home/pi/edgetpu_api/examples/coral_guide/mobilenet_ssd_v2_coco_quant_postprocess_edgetpu.tflite", help="path to the detection model")
    ap.add_argument("-l", "--label", nargs='?',
                    default="/home/pi/edgetpu_api/examples/coral_guide/coco_labels.txt", help="path to the labels file")
    ap.add_argument("--video_storage_addr", nargs='?', default="tcp://130.207.122.57:1429", help="address of videoStorageServer")
    ap.add_argument("--target_labels", nargs='*', default=["car", "bus", "truck"], help="list of target objects")
    ap.add_argument("--detection_threshold", nargs='?', default=0.2, help="the threshold used in object detection")
    args = ap.parse_args()

    vclient = VideoStorageClient(addr=args.video_storage_addr)
    engine = DetectionEngine(args.model)
    labels = ReadLabelFile(args.label)
    mot_tracker = Sort(max_age = 3, min_hits = 1)
    writer = None
    i = 0

    vs = cv2.VideoCapture(args.video)
    while True:
        (grabbed, frame) = vs.read()
        if not grabbed:
            break
        i += 1
        print(f"Processing on {i}th frame...", end='\r')

        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        ans = engine.DetectWithImage(image,
                                     threshold=args.detection_threshold,
                                     keep_aspect_ratio=False,
                                     resample=Image.NEAREST,
                                     relative_coord=False,
                                     top_k=10)

        logger.info("%.3f %d" % (engine.get_inference_time(), count_target_bbox(ans, labels, args.target_labels)))

        bboxs = generate_sort_tracker_bbox(ans, labels, args.target_labels)
        trackers = mot_tracker.update(numpy.asarray(bboxs))
        img_str = cv2.imencode('.jpg', frame)[1].tostring()
        vclient.push_frame(args.name, i, img_str, trackers.tolist())

    vs.release()
    # writer.release()
