import argparse
import zmq
import signal
import sys

from detection_func import *
from edgetpu.basic.basic_engine import BasicEngine

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
    context = None
    if args.output is not None:
        context = zmq.Context()
        socket = context.socket(zmq.PAIR)
        socket.connect(args.output)

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
        cleanup()
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)

    fps = FPS()
    while True:
        try:
            frame = stream.fetch_frame()
        except:
            break
        image = load_frame(frame)
        image_w, image_h = image.size
        resized_image = resize_frame(image, model_w, model_h)
        raw_result = inference(engine, resized_image)
        bboxes = post_inference(raw_result,
                                tensor_start_index,
                                target_labelIds,
                                args.threshold,
                                args.top_k, image_w, image_h)
        logging.info("Detection result: %s" % bboxes)
    
        if socket is not None:
            send_detection_results(socket, frame, bboxes)

        logging.debug("FPS: %.2f" % fps())

    cleanup()


if __name__ == '__main__':
    main()
