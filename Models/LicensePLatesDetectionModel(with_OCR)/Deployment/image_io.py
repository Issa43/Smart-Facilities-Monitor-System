import os

import cv2
import numpy as np

# cv2.imread / cv2.imwrite open files through the ANSI Windows API, so they fail
# silently on any path containing non-ASCII characters, such as the Arabic folder
# names this project was developed under. Reading the bytes ourselves and letting OpenCV decode
# them in memory sidesteps that. (VideoCapture/VideoWriter use ffmpeg and are fine.)


def imread_unicode(path, flags=cv2.IMREAD_COLOR):
    try:
        buffer = np.fromfile(str(path), dtype=np.uint8)
    except OSError as e:
        print("READ ERROR:", path, e)
        return None

    if buffer.size == 0:
        return None

    return cv2.imdecode(buffer, flags)


def imwrite_unicode(path, image):
    path = str(path)
    ext = os.path.splitext(path)[1] or ".jpg"

    ok, buffer = cv2.imencode(ext, image)
    if not ok:
        print("WRITE ERROR: cannot encode", path)
        return False

    try:
        buffer.tofile(path)
    except OSError as e:
        print("WRITE ERROR:", path, e)
        return False

    return True
