import argparse
import platform
import subprocess
import logging
import os
import glob
import time
import collections

#from edgetpu.detection.engine import DetectionEngine
from PIL import Image
from PIL import ImageDraw

ODLogger = logging.getLogger('ObjectDetector')

class FPS:
    def __init__(self,avarageof=50):
        self.frametimestamps = collections.deque(maxlen=avarageof)
    def __call__(self):
        self.frametimestamps.append(time.time())
        if(len(self.frametimestamps) > 1):
            return len(self.frametimestamps)/(self.frametimestamps[-1]-self.frametimestamps[0])
        else:
            return 0.0

# Function to read labels from text files.
def ReadLabelFile(file_path):
    with open(file_path, 'r', encoding="utf-8") as f:
        lines = f.readlines()
    ret = {}
    for line in lines:
        pair = line.strip().split(maxsplit=1)
        ret[int(pair[0])] = pair[1].strip()
    return ret


# Display result and output log.
def DisplayResult(ans, img, labels, output_name):
    ODLogger.debug('output_name = %s', output_name)

    if not ans:
        ODLogger.debug('No object detected!')
        return

    draw = ImageDraw.Draw(img)
    for obj in ans:
        ODLogger.debug('-----------------------------------------')
        if labels:
            ODLogger.debug(labels[obj.label_id])
            ODLogger.debug('score = %s', obj.score)
            box = obj.bounding_box.flatten().tolist()
            ODLogger.debug('box = %s', box)
            # Draw a rectangle.
            draw.rectangle(box, outline='red')
    img.save(output_name)

"""
def main():
    import logging.config
    logging.config.fileConfig('logging_config.ini', disable_existing_loggers=False)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--model', help='Path of the detection model.', required=True)
    parser.add_argument(
        '--label', help='Path of the labels file.')
    parser.add_argument(
        '--input', help='Directory of the input image.', required=True)
    parser.add_argument(
        '--output', help='Directory of the output image.')
    args = parser.parse_args()

    if not args.output:
        output_name = 'result'
    else:
        output_name = args.output

    # Initialize engine.
    engine = DetectionEngine(args.model)
    labels = ReadLabelFile(args.label) if args.label else None

    fps = FPS()		
    total = 0
    total_max = 100
    # Iterate images.
    for filename in glob.glob(os.path.join(args.input, '*.jpeg')):
        total += 1
        if total > total_max:
            break

        start_time = time.time()
        img = Image.open(filename)
        load_image_time = time.time()

        # Run inference.
        ans = engine.DetectWithImage(img, threshold=0.2, keep_aspect_ratio=False, resample=Image.NEAREST,
                relative_coord=False, top_k=10)
        
        detection_time = time.time()

        # Output result
        DisplayResult(ans, img, labels, os.path.join(output_name, os.path.basename(filename)))

        end_time = time.time()

        # Measure latency
        ODLogger.info('-----------------------------------------')
        ODLogger.info('inference_time = %s milliseconds', engine.get_inference_time())
        ODLogger.info('fps = %.2f', fps())
        ODLogger.info('load_image_time = %.3f seconds', load_image_time - start_time)
        ODLogger.info('detection_time = %.3f seconds', detection_time - load_image_time)
        ODLogger.info('display_time = %.3f seconds', end_time - detection_time)
        ODLogger.info('total_time = %.3f seconds', end_time - start_time)
        ODLogger.info('-----------------------------------------')
        

if __name__ == '__main__':
    main()
"""

