import argparse
import zmq
import signal
import sys
import threading

from queue import Queue
from detection_func import *
from edgetpu.basic.basic_engine import BasicEngine

isRunning = True

def log_qsize(q, name):
    logging.debug("Approximate size of the %s queue: %d" % (name, q.qsize()))


def wrapper_fetch(outq, stream):
    while isRunning:
        log_qsize(outq, "fetch")
        try:
            frame = stream.fetch_frame()
        except:
            break
        outq.put(frame)
    outq.put(None)


def wrapper_load_resize(inq, outq, model_w, model_h):
    while True:
        log_qsize(outq, "load_resize")
        frame = inq.get()
        if frame is None:
            break
        image = load_frame(frame)
        image_w, image_h = image.size
        resized_image = resize_frame(image, model_w, model_h)
        outq.put((frame, image, resized_image, image_w, image_h))
    outq.put(None)


def wrapper_fetch_load_resize(outq, stream, model_w, model_h):
    while isRunning:
        log_qsize(outq, "fetch_load_resize")
        try:
            frame = stream.fetch_frame()
        except:
            break
        image = load_frame(frame)
        image_w, image_h = image.size
        resized_image = resize_frame(image, model_w, model_h)
        outq.put((frame, image, resized_image, image_w, image_h))
    outq.put(None)


def wrapper_inference_post(inq, engine, tensor_start_index, target_labelIds, threshold, top_k, socket):
    fps = FPS()
    while True:
        image = inq.get()
        if image is None:
            break
        frame, original_image, resized_image, image_w, image_h = image
        raw_result = inference(engine, resized_image)
        bboxes = post_inference(raw_result,
                                tensor_start_index,
                                target_labelIds,
                                threshold,
                                top_k, image_w, image_h)
        logging.info("Detection result: %s" % bboxes)
        send_detection_results(socket, frame, bboxes)
        logging.debug("FPS: %.2f" % fps())


def arg_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels")
    parser.add_argument("--model")
    parser.add_argument("--imageSeq", nargs='?', default=None)
    parser.add_argument("--live", nargs='?', default=None)
    parser.add_argument("--cameraconfig", nargs='?', default=None)
    parser.add_argument("--userconfig", nargs='?', default=None)
    parser.add_argument("--output", nargs='?', default=None)

    parser.add_argument("--threshold", nargs='?', default=0.2)
    parser.add_argument("--top_k", nargs='?', default=10)
    args = parser.parse_args()
    return args


def main():
    import logging.config
    logging.config.fileConfig('logging_config.ini', disable_existing_loggers=False)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger('HttpUtil').setLevel(logging.INFO)

    args = arg_parse()

    if args.imageSeq is not None or args.live is not None:
        target_labelIds = get_target_labelIds(args.labels)
        engine = BasicEngine(args.model)
        model_w, model_h, tensor_start_index = engine_info(engine)
    else:
        logging.fatal("No valid stream input source")

    socket = None
    if args.output is not None:
        context = zmq.Context()
        socket = context.socket(zmq.PAIR)
        socket.connect(args.output)
        logging.info("Successfully connect to the second RPi.")

    if args.imageSeq is not None:
        stream = ImageSequenceStream(args.imageSeq)
    elif args.live is not None:
        stream = SingleCampusCameraStream(args.live, args.userconfig, args.cameraconfig)
        stream.login()
        logging.info("Successfully login into Campus Camera Stream --- %s" % args.live)

    def cleanup():
        if args.live is not None:
            stream.logout()
        if socket is not None:
            socket.close()
            context.term()

    def signal_handler(sig, frame):
        global isRunning
        isRunning = False
    signal.signal(signal.SIGINT, signal_handler)

    if args.imageSeq is not None:
        q = Queue()
        thread_fetch_load_resize = threading.Thread(target=wrapper_fetch_load_resize, args=(q, stream, model_w, model_h))
        thread_inference_post = threading.Thread(target=wrapper_inference_post, args=(q, engine, tensor_start_index, target_labelIds, args.threshold, args.top_k, socket))

        thread_inference_post.start()
        thread_fetch_load_resize.start()

        thread_fetch_load_resize.join()
        thread_inference_post.join()
    elif args.live is not None:
        q1 = Queue()
        q2 = Queue()
        thread_fetch = threading.Thread(target=wrapper_fetch, args=(q1, stream))
        thread_load_resize = threading.Thread(target=wrapper_load_resize, args=(q1, q2, model_w, model_h))
        thread_inference_post = threading.Thread(target=wrapper_inference_post, args=(q2, engine, tensor_start_index, target_labelIds, args.threshold, args.top_k, socket))

        thread_inference_post.start()
        thread_load_resize.start()
        thread_fetch.start()

        thread_fetch.join()
        thread_load_resize.join()
        thread_inference_post.join()

    cleanup()


if __name__ == '__main__':
    main()
