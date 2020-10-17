from adaptive_hist import adaptive_hist

import cv2

def coldstart(tgraph):
    # feature extraction:
    image = cv2.imread("coldstart.jpeg")
    hist = adaptive_hist(image)

    # vertex and edge add
    v1 = tgraph.addDetection("veh1", "cam1", 2000.0, "")
    v2 = tgraph.addDetection("veh1", "cam2", 2000.0, "")
    tgraph.linkDetection(v1, v2, "")
