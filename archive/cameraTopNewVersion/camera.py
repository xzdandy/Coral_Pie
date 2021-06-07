from threading import Timer


class RepeatingTimer(Timer):
    def run(self):
        while not self.finished.is_set():
            self.function(*self.args, **self.kwargs)
            self.finished.wait(self.interval)


class Camera:
    def __init__(self, id, latitude, longitude, pubsub_addr):
        self.id = id
        self.latitude = latitude
        self.longitude = longitude
        self.pubsub_addr = pubsub_addr

    def join_network(self, socket):
        socket.send_json({"request_type": "JOIN", "data": self.get_json_object()})
        return socket.recv_json()

    def get_neighbor_cams(self, socket):
        socket.send_json({"request_type": "GET_NEIGHBOR_CAMS", "data": self.get_json_object()})
        return socket.recv_json()

    def send_heartbeat(self, socket):
        socket.send_json({"request_type": "ALIVE", "data": self.get_json_object()})
        return socket.recv_json()

    def get_json_object(self):
        dict = {
            "id": self.id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "pubsub_addr": self.pubsub_addr
        }
        return dict

    def parse_response(self, response):
        if response:
            parsed = {}
            neighbors = response["response"]
            return list(neighbors)
        else:
            return []

    def get_cached_neighbor_cams(self):
        return self.response

    def camera_heartbeat_ticks(self, socket):
        self.send_heartbeat(socket)
        self.response = self.get_neighbor_cams(socket)

    def start_heartbeat(self, socket):
        self.t = RepeatingTimer(5.0, self.camera_heartbeat_ticks, (socket,))
        self.t.start()

    def stop_heartbeat(self):
        self.t.cancel()
