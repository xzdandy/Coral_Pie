import pubsub
import threading
from threading import Timer
import time


class RepeatingTimer(Timer):
    def run(self):
        while not self.finished.is_set():
            self.function(*self.args, **self.kwargs)
            self.finished.wait(self.interval)


cam1 = pubsub.PubSub("1", "tcp://127.0.0.1:8001", [], [])

cam2 = pubsub.PubSub("2", "tcp://127.0.0.1:8002", ["tcp://127.0.0.1:8001"], ["1"])

cam3 = pubsub.PubSub("3", "tcp://127.0.0.1:8003", ["tcp://127.0.0.1:8001"], ["1"])

cam4 = pubsub.PubSub("4", "tcp://127.0.0.1:8004", ["tcp://127.0.0.1:8002", "tcp://127.0.0.1:8003"], ["2", "3"])

cameras = [cam1, cam2, cam3, cam4]


def checkForNewMessages():
    for cam in cameras:
        received_message = cam.receiveData()
        if received_message != None:
            print(received_message)
            cam.publishMessage("Car detected")


def publishMessage():
    cam1.publishMessage("Car detected")


publish_thread = RepeatingTimer(5.0, publishMessage)
publish_thread.start()

check_messages_thread = RepeatingTimer(1.0, checkForNewMessages)
check_messages_thread.start()
