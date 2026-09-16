import queue
import threading
import time
from collections import Counter
from pathlib import Path

import cv2

import config
from debug_utils import save_debug
from direction import update_direction
from image_io import imread_unicode, imwrite_unicode
from models import load_models
from tracking import TrackState, tracks, cleanup_stale_tracks, reset_tracks, vehicle_number
from vehicle import match_vehicle_to_plate, simplify_vehicle_type

# Both engines expose the same interface (crop_plate, extract_plate_number, ...).
if config.OCR_ENGINE == "paddle":
    import ocr_paddle as ocr
else:
    import ocr

WINDOW_NAME = "Syrian Plate Recognition - Full Pipeline"
# Height of the window's title bar and borders, kept free above the frame.
WINDOW_TITLE_BAR = 40
# Used where the screen size can't be queried (anything but Windows).
FALLBACK_WORK_AREA = (0, 0, 1280, 720)

_window_open = False

GREEN = (0, 255, 0)        # plate read
ORANGE = (0, 200, 255)     # plate detected, OCR still trying


# ========================================================
# INPUT / OUTPUT
# ========================================================

def collect_inputs(path):
    """Split a file or a folder into (videos, images, skipped)."""
    path = Path(path)

    if path.is_dir():
        files = sorted(f for f in path.iterdir() if f.is_file())
    elif path.is_file():
        files = [path]
    else:
        return [], [], []

    videos, images, skipped = [], [], []
    for f in files:
        ext = f.suffix.lower()
        if ext in config.VIDEO_EXTS:
            videos.append(f)
        elif ext in config.IMAGE_EXTS:
            images.append(f)
        else:
            skipped.append(f)

    return videos, images, skipped


def output_path_for(src, keep_legacy_output):
    if keep_legacy_output:
        return Path(config.OUTPUT_PATH)

    out_dir = Path(config.OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = src.suffix if src.suffix.lower() in config.IMAGE_EXTS else ".mp4"
    return out_dir / f"{src.stem}_out{ext}"


def screen_work_area():
    """
    (left, top, width, height) of the desktop minus the taskbar.

    Measured in the same DPI-scaled units the OpenCV window uses, so the fit
    holds at 125%/150% display scaling too.
    """
    try:
        import ctypes
        from ctypes import wintypes

        SPI_GETWORKAREA = 0x0030
        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except (AttributeError, OSError):  # ctypes.windll exists only on Windows
        pass
    return FALLBACK_WORK_AREA


def fit_to_screen(frame, area):
    """Scale the frame down, never up, so all of it fits on the screen."""
    _, _, area_w, area_h = area
    h, w = frame.shape[:2]
    scale = config.WINDOW_SCREEN_FRACTION * min(area_w / w, (area_h - WINDOW_TITLE_BAR) / h)
    if scale >= 1.0:
        return frame
    size = (max(1, int(w * scale)), max(1, int(h * scale)))

    # INTER_AREA straight to a fractional size took ~12 ms a frame, as long as
    # the plate detector. By a whole factor it's fast, and the small step left
    # over looks fine with INTER_LINEAR.
    step = int(1 / scale)
    if step >= 2:
        frame = cv2.resize(frame, (w // step, h // step), interpolation=cv2.INTER_AREA)
    return cv2.resize(frame, size, interpolation=cv2.INTER_LINEAR)


class BackgroundVideoWriter:
    """
    cv2.VideoWriter fed from a worker thread.

    Encoding one 1080x1920 frame takes ~15 ms, a quarter of the pipeline loop;
    OpenCV releases the GIL while it encodes, so the loop moves on meanwhile.
    """

    def __init__(self, path, fourcc, fps, size):
        self.writer = cv2.VideoWriter(path, fourcc, fps, size)
        self.frames = queue.Queue(maxsize=8)  # a full queue makes the loop wait
        self.thread = threading.Thread(target=self._encode, daemon=True)
        self.thread.start()

    def _encode(self):
        while (frame := self.frames.get()) is not None:
            self.writer.write(frame)

    def write(self, frame):
        self.frames.put(frame)

    def release(self):
        self.frames.put(None)
        self.thread.join()
        self.writer.release()


def show(frame, wait_ms=None):
    """
    Draw the preview window, scaled to fit the screen. Returns True when the user pressed q.

    wait_ms=None doesn't wait: waitKey(1) sleeps until the next Windows timer tick,
    ~10 ms a frame, while pollKey still redraws the window and sees key presses.
    """
    global _window_open
    if not config.SHOW_WINDOW:
        return False

    area = screen_work_area()
    view = fit_to_screen(frame, area)
    cv2.imshow(WINDOW_NAME, view)

    # Centre the window when it first opens; after that the user can move it.
    if not _window_open:
        left, top, area_w, area_h = area
        view_h, view_w = view.shape[:2]
        cv2.moveWindow(WINDOW_NAME,
                       left + max(0, (area_w - view_w) // 2),
                       top + max(0, (area_h - view_h - WINDOW_TITLE_BAR) // 2))
        _window_open = True

    key = cv2.pollKey() if wait_ms is None else cv2.waitKey(wait_ms)
    return (key & 0xFF) == ord("q")


# ========================================================
# SHARED PIPELINE PIECES
# ========================================================

def detect_vehicles(vehicle_model, frame):
    """COCO detections filtered down to the vehicle classes we care about."""
    results = vehicle_model(
        frame, imgsz=config.YOLO_IMGSZ, conf=config.VEHICLE_CONF, verbose=False
    )

    detections = []
    for vres in results:
        if vres.boxes is None:
            continue
        for i in range(len(vres.boxes)):
            cls_id = int(vres.boxes.cls[i].cpu().numpy())
            if cls_id not in config.COCO_VEHICLE_CLASSES:
                continue
            vbox = vres.boxes.xyxy[i].cpu().numpy()
            detections.append((vbox, config.COCO_VEHICLE_CLASSES[cls_id]))

    return detections


def clamp_box(box, width, height):
    x1, y1, x2, y2 = box
    x1 = max(0, min(width - 1, int(x1)))
    y1 = max(0, min(height - 1, int(y1)))
    x2 = max(0, min(width - 1, int(x2)))
    y2 = max(0, min(height - 1, int(y2)))
    return x1, y1, x2, y2


def draw_summary(frame, summary, width, height, footer):
    cv2.rectangle(frame, (15, 15), (min(width - 15, 950), 60), (0, 0, 0), -1)
    cv2.putText(frame, summary[:80], (25, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, GREEN, 2)

    cv2.putText(frame, footer, (20, height - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)


# ========================================================
# VIDEO
# ========================================================

def process_video(src, out_path, model, vehicle_model):
    """Full pipeline: tracking + direction + multi-frame OCR voting."""
    reset_tracks()

    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        print("ERROR: Cannot open video:", src)
        return [], False

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not fps or fps <= 0:
        fps = 25.0

    print(f"[VIDEO] {src.name} -- {width} x {height} @ {fps:.2f} fps")

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = BackgroundVideoWriter(str(out_path), fourcc, fps, (width, height))

    line_p1 = (int(config.LINE_P1_RATIO[0] * width), int(config.LINE_P1_RATIO[1] * height))
    line_p2 = (int(config.LINE_P2_RATIO[0] * width), int(config.LINE_P2_RATIO[1] * height))

    frame_count = 0
    crossing_events = []
    started = time.perf_counter()
    quit_requested = False

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1

        # ====================================================
        # YOLO + ByteTrack (plates)
        # ====================================================

        if frame_count % config.DETECT_EVERY == 0:
            results = model.track(
                frame, imgsz=config.YOLO_IMGSZ, conf=config.YOLO_CONF, iou=0.45,
                persist=True, tracker="bytetrack.yaml", verbose=False
            )

            for result in results:
                if result.boxes is None or result.boxes.id is None:
                    continue

                boxes_xyxy = result.boxes.xyxy.cpu().numpy()
                track_ids = result.boxes.id.cpu().numpy().astype(int)
                confs = result.boxes.conf.cpu().numpy()

                for box, tid, conf in zip(boxes_xyxy, track_ids, confs):
                    x1, y1, x2, y2 = map(int, box)

                    if tid not in tracks:
                        tracks[tid] = TrackState()

                    st = tracks[tid]
                    st.box = (x1, y1, x2, y2)
                    st.last_seen_frame = frame_count
                    st.det_conf = float(conf)

                    centroid = ((x1 + x2) / 2, (y1 + y2) / 2)
                    crossed_now = update_direction(st, centroid, line_p1, line_p2, frame_count)
                    if crossed_now:
                        crossing_events.append({
                            "vehicle_id": st.vehicle_id,
                            "track_id": tid,
                            "frame": frame_count,
                            "direction": st.direction,
                            "plate": st.stable_text,
                            "vehicle_type": st.vehicle_type
                        })
                        print(f"[CROSSING] ID{st.vehicle_id or '?'} (track {tid}) -> {st.direction} "
                              f"(frame {frame_count}, plate={st.stable_text}, type={st.vehicle_type})")

        # ====================================================
        # Vehicle type model (COCO) -- runs less often than plate tracking
        # ====================================================

        if frame_count % config.VEHICLE_DETECT_EVERY == 0:
            vehicle_detections = detect_vehicles(vehicle_model, frame)

            for tid, st in tracks.items():
                if st.box is None:
                    continue
                matched_class = match_vehicle_to_plate(st.box, vehicle_detections)
                if matched_class:
                    st.vehicle_type_history.append(simplify_vehicle_type(matched_class))

                if st.vehicle_type_history:
                    most_common = Counter(st.vehicle_type_history).most_common(1)[0][0]
                    st.vehicle_type = most_common

        cleanup_stale_tracks(frame_count)

        # ====================================================
        # OCR for every active track
        # ====================================================

        # OCR also stalls the GPU: any ~100 ms pause between YOLO calls lets the
        # Quadro M2200 drop to a low power state, and the next plate inference
        # takes ~110 ms instead of ~17. So read only what can still change:
        #  - boxes the latest detection pass found -- a lost track's last box is
        #    road by now, and failed reads try every fallback, so they're slowest
        #  - plates not yet settled by LOCK_VOTES agreeing reads

        if frame_count % config.OCR_EVERY == 0:
            for tid, st in tracks.items():
                if st.box is None or frame_count - st.last_seen_frame >= config.DETECT_EVERY:
                    continue
                if st.stable_votes >= config.LOCK_VOTES:
                    continue

                x1, y1, x2, y2 = st.box
                plate = ocr.crop_plate(frame, x1, y1, x2, y2)

                detected_text, plate_type, conf = ocr.extract_plate_number(plate)
                st.plate_type = plate_type

                save_debug(plate, detected_text, plate_type, tid)

                if detected_text:
                    st.history.append((detected_text, conf))

                voted_text, votes = ocr.get_voted_text(st.history, config.MIN_VOTES)
                if voted_text:
                    st.stable_text = voted_text
                    st.stable_votes = votes
                    st.vehicle_id = vehicle_number(voted_text)

        # ====================================================
        # Draw the virtual crossing line
        # ====================================================

        cv2.line(frame, line_p1, line_p2, (255, 200, 0), 2)
        cv2.putText(frame, config.SIDE_POSITIVE_LABEL,
                    (line_p1[0] + 10, line_p1[1] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)
        cv2.putText(frame, config.SIDE_NEGATIVE_LABEL,
                    (line_p1[0] + 10, line_p1[1] + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)

        # ====================================================
        # Draw all tracks -- no ID/label until OCR succeeds
        # ====================================================

        for tid, st in tracks.items():
            if st.box is None:
                continue
            if frame_count - st.last_seen_frame > config.DETECT_EVERY * 2:
                continue

            x1, y1, x2, y2 = clamp_box(st.box, width, height)

            if st.stable_text is None:
                cv2.rectangle(frame, (x1, y1), (x2, y2), ORANGE, 2)
                continue

            cv2.rectangle(frame, (x1, y1), (x2, y2), GREEN, 3)

            centroid = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            cv2.circle(frame, centroid, 4, (0, 0, 255), -1)

            label = f"ID{st.vehicle_id} | {st.stable_text}"
            if st.vehicle_type:
                label += f" | {st.vehicle_type}"
            if st.direction:
                label += f" | {st.direction}"

            cv2.putText(frame, label, (x1, max(30, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, GREEN, 2)

        # ====================================================
        # Top-of-screen summary -- only vehicles with successful OCR
        # ====================================================

        # One entry per vehicle, even while the tracker has it split over two
        # tracks; the older track comes first and has the fuller state.
        active_texts = {}
        for st in tracks.values():
            if st.stable_text and frame_count - st.last_seen_frame <= config.DETECT_EVERY * 2:
                active_texts.setdefault(
                    st.vehicle_id,
                    f"ID{st.vehicle_id}:{st.stable_text}({st.vehicle_type or '?'},{st.direction or '?'})")
        summary = " | ".join(active_texts.values()) if active_texts else "Waiting for plate..."
        draw_summary(frame, summary, width, height, f"Frame: {frame_count}")

        out.write(frame)

        if show(frame):
            quit_requested = True
            break

    cap.release()
    out.release()

    elapsed = time.perf_counter() - started
    print(f"[VIDEO] {src.name} -- {frame_count} frames in {elapsed:.1f} s "
          f"({frame_count / elapsed:.1f} fps), {len(crossing_events)} crossing(s) -> {out_path}")

    return crossing_events, quit_requested


# ========================================================
# PHOTO
# ========================================================

def process_image(src, out_path, model, vehicle_model):
    """
    Single frame: no tracking, no direction, no multi-frame voting --
    every plate is read once and whatever OCR returns is what gets drawn.
    """
    frame = imread_unicode(src)
    if frame is None:
        print("ERROR: Cannot read image:", src)
        return [], False

    height, width = frame.shape[:2]

    results = model.predict(
        frame, imgsz=config.YOLO_IMGSZ, conf=config.YOLO_CONF, iou=0.45, verbose=False
    )
    vehicle_detections = detect_vehicles(vehicle_model, frame)

    records = []
    index = 0

    for result in results:
        if result.boxes is None:
            continue

        boxes_xyxy = result.boxes.xyxy.cpu().numpy()
        confs = result.boxes.conf.cpu().numpy()

        for box, det_conf in zip(boxes_xyxy, confs):
            index += 1
            x1, y1, x2, y2 = clamp_box(box, width, height)

            plate = ocr.crop_plate(frame, x1, y1, x2, y2)
            detected_text, plate_type, ocr_conf = ocr.extract_plate_number(plate)
            save_debug(plate, detected_text, plate_type, index)

            matched_class = match_vehicle_to_plate((x1, y1, x2, y2), vehicle_detections)
            vehicle_type = simplify_vehicle_type(matched_class) if matched_class else None

            records.append({
                "file": src.name,
                "index": index,
                "plate": detected_text,
                "plate_type": plate_type,
                "vehicle_type": vehicle_type,
                "det_conf": float(det_conf),
                "ocr_conf": float(ocr_conf),
            })
            print(f"  [{index}] plate={detected_text or '---'} type={plate_type} "
                  f"vehicle={vehicle_type or '?'} det={det_conf:.2f} ocr={ocr_conf:.2f}")

            if detected_text is None:
                cv2.rectangle(frame, (x1, y1), (x2, y2), ORANGE, 2)
                continue

            cv2.rectangle(frame, (x1, y1), (x2, y2), GREEN, 3)

            label = f"{detected_text}"
            if vehicle_type:
                label += f" | {vehicle_type}"
            cv2.putText(frame, label, (x1, max(30, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, GREEN, 2)

    found = [r["plate"] for r in records if r["plate"]]
    summary = " | ".join(found) if found else "No plate read"
    draw_summary(frame, summary, width, height, f"Photo: {src.name}")

    imwrite_unicode(out_path, frame)
    print(f"[PHOTO] {src.name} -- {index} plate box(es), {len(found)} read -> {out_path}")

    quit_requested = show(frame, config.IMAGE_DISPLAY_MS)
    return records, quit_requested


# ========================================================
# MAIN
# ========================================================

def main():
    input_path = Path(str(getattr(config, "INPUT_PATH", config.VIDEO_PATH)))
    videos, images, skipped = collect_inputs(input_path)

    print("=" * 70)
    print("Input:", input_path)

    if not videos and not images:
        if not input_path.exists():
            print("ERROR: path does not exist.")
        else:
            print("ERROR: no supported video or photo found.")
        print("Videos:", ", ".join(sorted(config.VIDEO_EXTS)))
        print("Photos:", ", ".join(sorted(config.IMAGE_EXTS)))
        print("=" * 70)
        return

    print(f"Found {len(videos)} video(s) and {len(images)} photo(s).")
    if skipped:
        print(f"Skipped {len(skipped)} unsupported file(s).")
    print("=" * 70)

    reader, model, vehicle_model = load_models()
    ocr.init_reader(reader)

    # A lone video keeps the old behaviour and overwrites config.OUTPUT_PATH.
    keep_legacy_output = len(videos) == 1 and not images and input_path.is_file()

    all_crossings = []
    all_plates = []
    outputs = []
    stopped = False

    for src in videos:
        out_path = output_path_for(src, keep_legacy_output)
        crossings, quit_requested = process_video(src, out_path, model, vehicle_model)
        all_crossings.extend(crossings)
        outputs.append(out_path)
        if quit_requested:
            stopped = True
            break

    if not stopped:
        for src in images:
            out_path = output_path_for(src, False)
            print(f"[PHOTO] {src.name}")
            records, quit_requested = process_image(src, out_path, model, vehicle_model)
            all_plates.extend(records)
            outputs.append(out_path)
            if quit_requested:
                stopped = True
                break

    cv2.destroyAllWindows()

    print("=" * 70)
    print("FINISHED" if not stopped else "STOPPED BY USER")
    for out_path in outputs:
        print("  Output:", out_path)
    print("Debug folder:", config.DEBUG_FOLDER)

    if all_plates:
        read_ok = [r for r in all_plates if r["plate"]]
        print(f"Photos: {len(read_ok)}/{len(all_plates)} plate box(es) read")
        for r in read_ok:
            print(f"  {r['file']} [{r['index']}] | plate={r['plate']} | "
                  f"type={r['plate_type']} | vehicle={r['vehicle_type']}")

    if videos:
        print(f"Total crossing events: {len(all_crossings)}")
        for ev in all_crossings:
            print(f"  ID{ev['vehicle_id'] or '?'} (track {ev['track_id']}) | {ev['direction']} | frame {ev['frame']} | "
                  f"plate={ev['plate']} | type={ev['vehicle_type']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
