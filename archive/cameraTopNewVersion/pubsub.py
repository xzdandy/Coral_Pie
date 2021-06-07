import zmq


class PubSub:
    def __init__(self, id, bind_url, connect_urls, subscribe_to):
        self.id = id
        self.pub_context = zmq.Context()
        self.pub_socket = self.pub_context.socket(zmq.PUB)
        self.pub_socket.bind(bind_url)

        self.sub_context = zmq.Context()
        self.sub_socket = self.sub_context.socket(zmq.SUB)
        for url in connect_urls:
            self.sub_socket.connect(url)
        for publisher in subscribe_to:
            self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, publisher)

    def publishMessage(self, message):
        self.pub_socket.send_string('%s-%s' % (self.id, message))

    def receiveData(self):
        received_data = self.sub_socket.recv_string()
        topic, message_data = received_data.split("-")
        return (topic, message_data)
