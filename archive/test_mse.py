import logging
import os
import argparse
import numpy as np
import time

from PIL import Image

MSELogger = logging.getLogger('MSEFrames')


def openAndResize(filename, width=300, height=300, sample=Image.NEAREST):
    img = Image.open(filename)
    resized_img = img.resize((width, height), sample)
    return resized_img

def imageIterator(num, in_dir):

    lfilename = os.path.join(in_dir, '%06d.jpeg' % 0)
    lastImage = np.asarray(openAndResize(lfilename))
    for i in range(1,num):
        cfilename = os.path.join(in_dir, '%06d.jpeg' % i)
        currentImage = np.asarray(openAndResize(cfilename))

        time1 = time.time()
        mse_standard = np.square(np.subtract(currentImage, lastImage)).mean()
        time2 = time.time()

        MSELogger.info('MSE between %s and %s: %f' % 
                (lfilename, cfilename, mse_standard))
        MSELogger.info('Time cost: %.3f' % 
                (time2-time1))

        lastImage = currentImage
        lfilename = cfilename



if __name__ == '__main__':
    import logging.config
    logging.config.fileConfig('logging_config.ini', disable_existing_loggers=False)
    
    parser = argparse.ArgumentParser()
    parser.add_argument(
            '--input', nargs='?', type=str,
            default='/home/pi/edgetpu_api/examples/campus_image/ferst_hemphill',
            help='Directory of input images')

    args = parser.parse_args()

    num = 100
    imageIterator(num, args.input)

    
