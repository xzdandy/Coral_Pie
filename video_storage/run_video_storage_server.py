#!/usr/bin/env python3
import argparse
import signal
import sys

from video_storage import VideoStorageServer

if __name__ == '__main__':
    import logging
    import logging.config
    logging.config.fileConfig('logging_config.ini', disable_existing_loggers=False)
    logging.getLogger('PIL').setLevel(logging.WARNING)  # Disable the debug logging from PIL

    parser = argparse.ArgumentParser()
    parser.add_argument("--addr", nargs="?", default="tcp://*:1429", help="IP:PORT the server should listen on")
    parser.add_argument("--dir", nargs="?", default="videoStore", help="Base directory to store the video")
    parser.add_argument("--threads", nargs="?", default=1, help="Number of worker threads")
    args = parser.parse_args()

    vserver = VideoStorageServer(addr=args.addr, basedir=args.dir)

    def signal_handler(sig, frame):
        print("VideoStorageServer is exiting...")
        vserver.exit()
    signal.signal(signal.SIGINT, signal_handler)

    vserver.run(threads = args.threads)
