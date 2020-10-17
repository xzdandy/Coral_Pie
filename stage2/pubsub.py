import zmq
import threading
import json
import time
import logging
import sys

from camera_topology_client import *

class PubSub:
    def __init__(self, cname, pubsub_addr, 
            context=zmq.Context(), config='../config/cameras.json', top_addr='tcp://130.207.122.57:5555'):

        self.logger = logging.getLogger(__name__)
        
        try:
            with open(config) as f:
                cameraconfig = json.load(f)
            lat, lon = cameraconfig[cname]['location']
        except Exception as e:
            self.logger.fatal(e)
            sys.exit(-1)

        self.cname = cname
        self.context = context
        self.connect_urls = []
        self.subscribe_to = []
        self.lock = threading.Lock()
        self.top_client = Camera(cname, lat, lon, pubsub_addr) 
        self.top_socket = context.socket(zmq.REQ)
        self.top_socket.connect(top_addr)
        self.top_client.join_network(self.top_socket)

        self.pub_socket = context.socket(zmq.PUB)
        self.pub_socket.bind('tcp://*:%s' % pubsub_addr.split(':')[2])
        self.sub_socket = None

        self.thread = RepeatingTimer(5.0, self.routine_check)
        self.thread.start()

    def routine_check(self):
        #self.lock.acquire()

        self.top_client.send_heartbeat(self.top_socket)
        response = self.top_client.get_neighbor_cams(self.top_socket)['response']

        new_subscribe_to = sorted(list(response))
        new_connect_urls = sorted(list([response[t]['pubsub_addr'] for t in new_subscribe_to]))

        print(new_subscribe_to, new_connect_urls)

        if new_connect_urls != self.connect_urls:
            self.connect_urls = new_connect_urls
            self.sub_socket = self.context.socket(zmq.SUB)
            for url in self.connect_urls:
                self.sub_socket.connect(url)
        
        if new_subscribe_to != self.subscribe_to:
            self.subscribe_to = new_subscribe_to
            self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, '')
            for publisher in self.subscribe_to:
                self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, publisher)

        #self.lock.release()

    
    def publishMessage(self, message):
        self.pub_socket.send_string('%s|%s' % (self.cname, message))

    def receiveData(self):
        #self.lock.acquire()
        while self.sub_socket is None:
            time.sleep(1)
        received_data = self.sub_socket.recv_string()
        #self.lock.release()
        try:
            topic, message_data = received_data.split("|")
        except Exception as e:
            self.logger.error('Error when parsing received messages: %s' % e)
            self.logger.error(received_data)

        return (topic, message_data)
