from typing import Tuple, List, Dict, Optional

import osmnx as ox


class BaseMap:
    """
    Store the base road map under the camera network

    Example edge attributes from osmnx:
    {'osmid': 9265808, 'name': 'Hemphill Avenue Northwest',
    'highway': 'tertiary', 'maxspeed': '25 mph', 'oneway': False,
    'length': 28.716, 'geometry': ..., 'bearing': 321.6}
    """

    def __init__(self, latlon: Tuple[float, float], dist: float):
        ox.config(log_console=False, use_cache=True)
        G = ox.graph_from_point(latlon, dist=dist, network_type='drive')
        # Bearing represents angle in degrees (clockwise) between north
        # and the direction from the origin node to the destination node.
        self.G = ox.bearing.add_edge_bearings(G)

    def plot_graph_routes(self, routes: List[List], **kwargs):
        # ox.plot_graph_routes can not print one route
        if len(routes) > 1:
            ox.plot_graph_routes(self.G, routes=routes, **kwargs)
        elif len(routes) == 1:
            ox.plot_graph_route(self.G, route=routes[0], **kwargs)


class CameraOverlay(BaseMap):
    """
    Store the camera topology given a basemap
    """

    def __init__(self, *args, **kwargs):
        self.cameraInfo = {}
        super(CameraOverlay, self).__init__(*args, **kwargs)
        self.node_camera = self._NodeCamera(self.G)
        self.edge_camera = self._EdgeCamera(self.G)

    class _NodeCamera:
        """
        Maintain the state of whether a camera is equipped at a node in the
        graph (intersection in the real life).
        """

        def __init__(self, map):
            self.G = map
            self._camera_to_node = {}

        @property
        def camera_to_node(self):
            return self._camera_to_node

        def add_camera(self, node: int, name: str):
            self.camera_to_node[name] = node
            if 'cameras' not in self.G.nodes[node]:
                self.G.nodes[node]['cameras'] = [name]
            else:
                self.G.nodes[node]['cameras'].append(name)

        def get_cameras(self, node: int) -> List[str]:
            if 'cameras' in self.G.nodes[node]:
                return self.G.nodes[node]['cameras']
            else:
                return []

        def remove_camera(self, name: str):
            node = self.camera_to_node.pop(name, None)
            if node is not None:
                self.G.nodes[node]['cameras'].remove(name)

        def is_equipped_cameras(self, node: int) -> bool:
            return 'cameras' in self.G.nodes[node] and \
                len(self.G.nodes[node]['cameras']) > 0

    class _EdgeCamera:
        """
        Maintain the state of whether a camera is equipped at an edge
        in the graph (along the road in the real life).
        """

        def __init__(self, map):
            self.G = map
            self._camera_to_edge = {}

        @property
        def camera_to_edge(self):
            return self._camera_to_edge

        def add_camera(self, edge: Tuple, name: str,
                       latlon: Tuple[float, float]):
            self.camera_to_edge[name] = edge
            if 'cameras' not in self.G.edges[edge]:
                self.G.edges[edge]['cameras'] = {'from': edge[0],
                                                 'list': []}
            src = self.G.edges[edge]['cameras']['from']
            assert (src == edge[0] or src == edge[1]), \
                'Inconsistent edge information, src: %s, edge: %s' \
                % (src, edge)

            # We use this distance to estimate the relative camera location
            # if multiple cameras are located on the same edge.
            src_latlon = (self.G.nodes[src]['y'], self.G.nodes[src]['x'])
            dist_src = ox.distance.euclidean_dist_vec(*src_latlon, *latlon)

            # The front cameras in camera_list in close to the src node.
            camera_list = self.G.edges[edge]['cameras']['list']
            if len(camera_list) == 0:
                camera_list.append((name, dist_src))
            else:
                for idx, val in enumerate(camera_list):
                    if dist_src < val[1]:
                        break
                camera_list.insert(idx, (name, dist_src))

        def get_cameras(self, edge) -> List[str]:
            if 'cameras' in self.G.edges[edge]:
                camera_list = self.G.edges[edge]['cameras']['list']
                node_from = self.G.edges[edge]['cameras']['from']
                if edge[0] == node_from:
                    return list([x[0] for x in camera_list])
                elif edge[1] == node_from:
                    return list([x[0] for x in reversed(camera_list)])
                else:
                    assert (node_from == edge[0] or node_from == edge[1]), \
                        'Inconsistent edge information, src: %s, edge: %s' \
                        % (src, edge)
            else:
                return []

        def remove_camera(self, name: str):
            edge = self.camera_to_edge.pop(name, None)
            if edge is not None:
                camera_list = self.G.edges[edge]['cameras']['list']
                self.G.edges[edge]['cameras']['list'] = \
                    list(filter(lambda x: x[0] != name, camera_list))

        def is_equipped_cameras(self, edge: Tuple) -> bool:
            return 'cameras' in self.G.edges[edge] and \
                len(self.G.edges[edge]['cameras']['list']) > 0

    def update_camera(self, name: str, latlon: Tuple[float, float],
                      metadata: Dict = {},
                      max_intersection_dist: float = 5,
                      max_lane_dist: float = 5) -> Tuple[bool, bool]:
        """
        return Tuple(a: bool, b: bool): a indicates whether the camera is
        successfully added to the road network. b indicates whether the
        topology has changed.
        """
        # We simply remove the existing camera and calculate the new
        # position. And topology_change is always true if success.
        # TODO: decide whether the topology actually changes.
        if name in self.cameraInfo:
            self.remove_camera(name)

        success = False
        nearest_node, dist = ox.get_nearest_node(self.G, latlon, return_dist=True)
        if dist < max_intersection_dist:
            self.node_camera.add_camera(nearest_node, name)
            success = True
        else:
            u, v, key, dist = ox.get_nearest_edge(self.G, latlon, return_dist=True)
            if dist < max_lane_dist:
                self.edge_camera.add_camera((u, v, key), name, latlon)
                success = True

        if success:
            self.cameraInfo[name] = {'latlon': latlon, 'meta': metadata}
        return success, success

    def remove_camera(self, name: str):
        """
        Remove a specific camera from the topology.
        """
        self.cameraInfo.pop(name, None)
        self.node_camera.remove_camera(name)
        self.edge_camera.remove_camera(name)

    class _DFSStack:

        def __init__(self, stack: List[Tuple]):
            self.in_stack = set([x[0] for x in stack])
            # no copy
            self.stack = stack

        def __len__(self):
            return len(self.stack)

        def __contains__(self, node):
            return node in self.in_stack

        def pop(self):
            ans = self.stack.pop()
            self.in_stack.remove(ans[0])
            return ans

        def append(self, x: Tuple):
            assert (x[0] not in self.in_stack), '%s already in stack' % x
            self.stack.append(x)
            self.in_stack.add(x[0])

    def _draw_routes(self, start_camera, routes, filename):
        start_node = None
        if start_camera in self.node_camera.camera_to_node:
            start_node = self.node_camera.camera_to_node[start_camera]
        nc = []
        for node in self.G.nodes:
            if node == start_node:
                nc.append('c')
            elif self.node_camera.is_equipped_cameras(node):
                nc.append('r')
            else:
                nc.append('b')
        ec = []
        for edge in self.G.edges:
            if self.edge_camera.is_equipped_cameras(edge):
                ec.append('r')
            else:
                ec.append('#999999')
        self.plot_graph_routes(routes=routes,
                               node_color=nc, node_zorder=3,
                               edge_color=ec, bgcolor='w', show=False,
                               save=True, filepath=filename)

    def get_downstream_cameras(self, name: str, direction: float = -1,
                               max_dfs: int = 5,
                               max_bearing: float = 90,
                               debug: bool = False) -> List[str]:
        res = []
        routes = None
        if name in self.node_camera.camera_to_node:
            node = self.node_camera.camera_to_node[name]
            res, routes = self.get_downstream_cameras_from_node(node, direction,
                                                                max_dfs, max_bearing,
                                                                debug)
        elif name in self.edge_camera.camera_to_edge:
            res, routes = self.get_downstream_cameras_from_edge(name, direction,
                                                                max_dfs, max_bearing,
                                                                debug)
        if debug and len(res) > 0:
            self._draw_routes(name, routes, '%s.png' % name)
        return res

    def get_downstream_cameras_from_edge(self, name: str,
                                         direction: float = -1,
                                         max_dfs: int = 5,
                                         max_bearing: float = 90,
                                         debug: bool = False) \
            -> Tuple[List[str], List[int]]:
        """
        When the camera is in the middle of the edge, then if it is surrounded
        by two other cameras, then they will the downstream cameras.
        So we only need to handle, when the camera is the first or the last on
        the edge. And it can be solved by doing DFS from the close node and
        remove the self.
        """
        if direction < 0 or direction > 360:
            undirectional = True
        else:
            undirectional = False

        # edge -> u, v, key
        edge = self.edge_camera.camera_to_edge[name]
        c_list = self.edge_camera.get_cameras(edge)
        idx = c_list.index(name)
        routes = None
        if undirectional:
            if idx > 0 and idx < len(c_list) - 1:
                res = [clist[idx-1], clist[idx+1]]
            elif len(c_list) == 1:
                # DFS both directions and remove self
                res, routes = self.get_downstream_cameras_from_node(
                    edge[0], -1, max_dfs, max_bearing, debug)
                res1, routes1 = self.get_downstream_cameras_from_node(
                    edge[1], -1, max_dfs, max_bearing, debug)
                res += res1
                routes += routes1
                res = list(filter(lambda x: x != name, res))
            elif idx == 0:
                # DFS from u, the reason is the DFS to v will stop after
                # reaching the next camera on the edge.
                res, routes = self.get_downstream_cameras_from_node(
                    edge[0], -1, max_dfs, max_bearing, debug)
                res.remove(name)
                res.append(c_list[1])
            else:
                # DFS from v
                res, routes = self.get_downstream_cameras_from_node(
                    edge[1], -1, max_dfs, max_bearing, debug)
                res.remove(name)
                res.append(c_list[-2])
        else:
            edge_bearing = self.G.edges[edge]['bearing']
            # u->v
            if abs(edge_bearing - direction) < max_bearing:
                # last one
                if idx == len(c_list) - 1:
                    res, routes = self.get_downstream_cameras_from_node(
                        edge[1], -1, max_dfs, max_bearing, debug)
                    res.remove(name)
                else:
                    res = [c_list[idx+1]]
            # v->u
            elif abs((edge_bearing + 180) % 360 - direction) < max_bearing:
                # first one
                if idx == 0:
                    res, routes = self.get_downstream_cameras_from_node(
                        edge[0], -1, max_dfs, max_bearing, debug)
                    res.remove(name)
                else:
                    res = [c_list[idx-1]]
            else:
                res = []
        return res, routes

    def _generate_routes(self, dest_nodes, start_node, parent_node):
        route_list = []
        for curr_node in dest_nodes:
            route = []
            while curr_node != start_node:
                route.append(curr_node)
                curr_node = parent_node[curr_node]
            route.append(start_node)
            route.reverse()
            route_list.append(route)
        return route_list

    def get_downstream_cameras_from_node(self, node: int,
                                         direction: float = -1,
                                         max_dfs: int = 5,
                                         max_bearing: float = 90,
                                         debug: bool = False) \
            -> Tuple[List[str], List[int]]:
        """
        direction is similar to the bearing in osmnx, angle in degrees
        (clockwise) between north and the direction.
        If direction is not valid [0, 360], it is ignored
        (i.e., DFS for all outgoing edges).
        """

        if direction < 0 or direction > 360:
            undirectional = True
        else:
            undirectional = False

        res = []
        parent_node = {}
        dest_nodes = []
        visited = set()
        start_node = node
        stack = self._DFSStack([(start_node, 0)])
        first_edge = True

        while len(stack) != 0:
            node, dist = stack.pop()
            visited.add(node)

            outgoing_edges = self.G.out_edges(node, keys=True, data=True)

            if not undirectional and first_edge:
                outgoing_edges = list(outgoing_edges)
                outgoing_edges.sort(key=lambda tup:
                                    abs(tup[3]['bearing'] - direction))
                if abs(outgoing_edges[0][3]['bearing'] - direction) \
                        > max_bearing:
                    # no outgoing edge found
                    return []
                else:
                    outgoing_edges = outgoing_edges[0:1]
                    first_edge = False

            for u, v, key, d in outgoing_edges:
                if self.edge_camera.is_equipped_cameras((u, v, key)):
                    res.append(self.edge_camera.get_cameras((u, v, key))[0])
                    dest_nodes.append(u)
                    continue

                if v in visited:
                    continue

                if self.node_camera.is_equipped_cameras(v):
                    parent_node[v] = u
                    res += self.node_camera.get_cameras(v)
                    dest_nodes.append(v)
                    visited.add(v)
                elif dist + 1 <= max_dfs and v not in stack:
                    parent_node[v] = u
                    stack.append((v, dist + 1))

        routes = []
        if debug:
            routes = self._generate_routes(dest_nodes, start_node, parent_node)

        return res, routes


def main():
    camera_layer = CameraOverlay(
        latlon=(33.775259139909664, -84.39705848693849), dist=500)
    camera_layer.update_camera(name='ferst_hemphill',
                               latlon=(33.778406, -84.401304))
    camera_layer.update_camera(name='ferst_state',
                               latlon=(33.778279, -84.399226))
    camera_layer.update_camera(name='ferst_crc',
                               latlon=(33.775426, -84.402559))
    camera_layer.update_camera(name='ferst_atlantic',
                               latlon=(33.778254, -84.397794))

    assert (set(camera_layer.get_downstream_cameras('ferst_hemphill',
                                                    debug=False))
            == set(['ferst_state', 'ferst_crc']))
    assert (camera_layer.get_downstream_cameras('ferst_hemphill', direction=90,
                                                debug=False)
            == ['ferst_state'])
    assert (set(camera_layer.get_downstream_cameras('ferst_state', debug=True))
            == set(['ferst_hemphill', 'ferst_atlantic']))
    assert (camera_layer.get_downstream_cameras('ferst_state', direction=90,
                                                debug=False)
            == ['ferst_atlantic'])
    assert (camera_layer.get_downstream_cameras('ferst_crc', debug=False)
            == ['ferst_hemphill'])

    camera_layer.remove_camera('ferst_state')

    assert (set(camera_layer.get_downstream_cameras('ferst_hemphill', debug=False))
            == set(['ferst_crc', 'ferst_atlantic']))
    assert (camera_layer.get_downstream_cameras('ferst_hemphill', direction=90,
                                                debug=False)
            == ['ferst_atlantic'])


if __name__ == '__main__':
    main()
