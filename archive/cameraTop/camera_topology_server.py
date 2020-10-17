# pylint: skip-file
from threading import Timer
from datetime import datetime
import zmq
import time
import osmnx as ox
import numpy as np
import networkx as nx
from networkx.readwrite import json_graph
import matplotlib.pyplot as plt
import re
import json
import random
import os
ox.config(log_console=False, use_cache=True)


class RepeatingTimer(Timer):
    def run(self):
        while not self.finished.is_set():
            self.function(*self.args, **self.kwargs)
            self.finished.wait(self.interval)


def backtrace_route(parents, start, end):
    route = []
    currentNode = start
    count = 0
    while currentNode != end and count < 20:
        route.append(currentNode)
        currentNode = parents[currentNode]
        count += 1
    route.append(currentNode)
    route.reverse()
    # print("Route:{}".format(route))
    return route


def dfs(graph, camera_nodes, cname):
    data = {}
    visited = []
    stack = []
    parents = {}

    # the id of the node in the Graph
    camera_node_id = camera_nodes[cname]["node_id"]
    stack.append(camera_node_id)

    while len(stack) != 0:
        node = stack.pop()
        visited.append(node)

        # vehicle can reach this node
        incoming_edges = G.in_edges(node)

        for edge in incoming_edges:
            # edge is (v1, v2) where v1 -> v2
            incoming_neighbor = edge[0]
            if incoming_neighbor in visited:
                continue
            if incoming_neighbor in inverse_camera_nodes:
                name = inverse_camera_nodes[incoming_neighbor]
                camera = camera_nodes[name]

                if camera["is_active"] is True:
                    parents[incoming_neighbor] = node
                    btroute = backtrace_route(parents, incoming_neighbor, camera_node_id)
                    if len(btroute) < 10:
                        data[name] = {"cam_id": incoming_neighbor, "route": btroute, "pubsub_addr": camera["pubsub_addr"]}
                elif incoming_neighbor not in stack:
                    parents[incoming_neighbor] = node
                    stack.append(incoming_neighbor)

            elif incoming_neighbor not in stack:
                parents[incoming_neighbor] = node
                stack.append(incoming_neighbor)

    nc = ['r' if node in inverse_camera_nodes else 'b' for node in G.nodes]
    route_list = [neighbor_cam["route"] for _, neighbor_cam in data.items()]
    ox.plot_graph_routes(G, routes=route_list, node_color=nc, node_zorder=3, orig_dest_node_color=['r', 'k']*len(route_list),
                         show=False, save=True, filename=cname)

    return data


def add_camera_to_network(camera):
    print("Received join request from: %s" % camera["id"])
    if camera["id"] not in camera_nodes:
        nearest_node = int(ox.get_nearest_node(G, (float(camera["latitude"]), float(camera["longitude"]))))
        print("Nearest node on map: {}".format(nearest_node))
        camera_nodes[camera["id"]] = {"node_id": nearest_node,
                                      "pubsub_addr": camera["pubsub_addr"],
                                      "is_active": True,
                                      "last_heartbeat_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        # int -> str
        inverse_camera_nodes[nearest_node] = camera["id"]
        return {"response": "{} added successfully".format(camera["id"])}
    else:
        return {"response": "{} already part of network".format(camera["id"])}


def get_neighbor_cams(camera):
    print("Received neighbor request from: %s" % camera["id"])
    # connected_edges = [(u, v, k) for u, v, k in G.edges if v == camera_nodes[camera["id"]]]
    # print("Connected edges: {}".format(connected_edges))
    neighbor_cams = dfs(G, camera_nodes, camera["id"])

    return {"response": neighbor_cams}


def alive_check(camera):
    camera_nodes[camera["id"]]["last_heartbeat_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return camera_nodes[camera["id"]]


def check_for_alive_cameras():
    for cname, camera in camera_nodes.items():
        duration_since_last_heartbeat = datetime.now() - datetime.strptime(camera["last_heartbeat_check"], "%Y-%m-%d %H:%M:%S")
        if duration_since_last_heartbeat.seconds > 10:
            camera["is_active"] = False
            print("{} DIED".format(cname))
        else:
            camera["is_active"] = True
            print("{} ALIVE".format(cname))


context = zmq.Context()
socket = context.socket(zmq.REP)
socket.bind("tcp://*:5555")

G = ox.graph_from_point((33.775259139909664, -84.39705848693849), distance=500, network_type='drive')

camera_nodes = {}
inverse_camera_nodes = {}

t = RepeatingTimer(5.0, check_for_alive_cameras)
t.start()


while True:
    # receive join request from camera
    message = socket.recv_json()
    if message["request_type"] == "JOIN":
        response = add_camera_to_network(message["data"])
        socket.send_json(response)
    elif message["request_type"] == "GET_NEIGHBOR_CAMS":
        response = get_neighbor_cams(message["data"])
        socket.send_json(response)
    elif message["request_type"] == "ALIVE":
        response = alive_check(message["data"])
        socket.send_json(response)
    else:
        socket.send_json({"response": "Invalid request"})
