import logging
import time
import zmq
import os
import io
import sys
import collections

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from threading import Thread


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
    def _decorator(self, *args, **kwargs):
        time1 = time.time()
        ret = f(self, *args, **kwargs)
        time2 = time.time()
        self.logger.debug("%s function took %.3f ms" % (f.__name__, (time2 - time1) * 1000.0))
        return ret
    return _decorator


class VideoStorageClient:
    def __init__(self, addr, context=zmq.Context()):
        self.logger = logging.getLogger(__name__)
        self.socket = context.socket(zmq.DEALER)
        self.socket.connect(addr)

    def push_frame(self, camera_name, frame_id, frame, bboxes):
        self.socket.send_pyobj((camera_name, frame_id, frame, bboxes), flags=zmq.NOBLOCK)


class VideoStorageServer:
    colorNames = ['aqua', 'black', 'blue', 'fuchsia',
                  'gray', 'green', 'lime', 'maroon',
                  'navy', 'olive', 'purple', 'red',
                  'silver', 'teal', 'white', 'yellow']

    def __init__(self, addr="tcp://*:1429", basedir="videoStore"):
        self.logger = logging.getLogger(__name__)

        self.font = ImageFont.truetype("./FiraCode-Regular.otf", 24)
        self.basedir = basedir
        if not self.createDir(self.basedir):
            sys.exit(-1)

        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.DEALER)
        self.socket.bind(addr)

    def run(self, threads=2):
        self.fps = FPS()
        self.workers = []
        self.polling_stopped = False
        self.rcvd_objs = []
        for i in range(0, threads):
            thread = Thread(target=self.listen_thread)
            self.workers.append(thread)
            thread.start()
        self.polling_thread = Thread(target=self.polling)
        self.polling_thread.start()

    def exit(self):
        self.polling_stopped = True
        self.polling_thread.join()
        for thread in self.workers:
            thread.join()

    def polling(self):
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        while not self.polling_stopped:
            events = dict(poller.poll(100))
            if len(events) == 0:
                continue
            if self.socket not in events:
                continue
            while True:
                try:
                    recv_obj = self.socket.recv_pyobj(flags=zmq.NOBLOCK)
                except zmq.ZMQError:
                    break
                self.rcvd_objs.append(recv_obj)

    def listen_thread(self):
        while len(self.rcvd_objs) > 0 or not self.polling_stopped:
            if len(self.rcvd_objs) > 0:
                recv_obj = self.rcvd_objs.pop()
                camera_name, frame_id, frame, bboxes = recv_obj
                filename = self.check_path(camera_name, frame_id)
                if not filename:
                    continue

                self.draw_frame(filename, frame, bboxes)
                self.logger.debug("FPS: %.2f" % self.fps())

    @timing
    def draw_frame(self, filename, frame, bboxes):
        image = Image.open(io.BytesIO(frame))
        draw = ImageDraw.Draw(image)
        for bbox in bboxes:
            x1, y1, x2, y2, vid = bbox
            color = self.colorNames[int(vid) % len(self.colorNames)]
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
            draw.text([x1, y1], str(vid), fill="red", font=self.font)
        image.save(filename, "JPEG")
        self.logger.debug("Successfully write %s" % filename)

    def check_path(self, camera_name, frame_id, overwrite=True):
        frame_dir = os.path.join(self.basedir, camera_name)
        if not os.path.isdir(frame_dir) and not self.createDir(frame_dir):
            return False
        frame_path = os.path.join(frame_dir, "%06d.jpeg" % frame_id)
        if not overwrite and os.path.exists(frame_path):
            self.logger.error("File %s exists!" % frame_path)
            return False
        return frame_path

    def createDir(self, dir):
        try:
            os.makedirs(dir)
        except FileExistsError:
            self.logger.warning("%s already exists" % dir)
            return True
        except Exception as e:
            self.logger.fatal("Exception occurred when creating directory %s: %s" % (dir, e))
            return False
        return True


if __name__ == "__main__":
    import logging.config
    logging.config.fileConfig('logging_config.ini', disable_existing_loggers=False)
    logging.getLogger('PIL').setLevel(logging.WARNING)  # Disable the debug loggi   ng from PIL

    vserver = VideoStorageServer()
    vserver.run()
    vclient = VideoStorageClient("tcp://localhost:1429")
    with open("test.jpg", "rb") as f:
        frame = f.read()
    for i in range(200):
        vclient.push_frame("ferst_atlantic", i, frame, [[100+i*10, 200+i*10, 200+i*10, 300+i*10, i]])
        time.sleep(0.080)
        vclient.push_frame("ferst_state", i+10, frame, [[100+i*10, 200+i*10, 200+i*10, 300+i*10, i+10]])
        time.sleep(0.080)
    vserver.exit()
