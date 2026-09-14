from collections import Counter

import cv2

import config
import ocr
from debug_utils import save_debug
from direction import update_direction
from models import load_models
from tracking import TrackState, tracks, cleanup_stale_tracks
from vehicle import match_vehicle_to_plate, simplify_vehicle_type


def main():
    video_path = str(config.VIDEO_PATH)
    output_path = str(config.OUTPUT_PATH)

    reader, model, vehicle_model = load_models()
    ocr.init_reader(reader)

    print("=" * 70)
    print("Opening video...")
    print("=" * 70)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("ERROR: Cannot open video:", video_path)
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"Resolution: {width} x {height}")
    print(f"FPS: {fps}")
    print("=" * 70)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    line_p1 = (int(config.LINE_P1_RATIO[0] * width), int(config.LINE_P1_RATIO[1] * height))
    line_p2 = (int(config.LINE_P2_RATIO[0] * width), int(config.LINE_P2_RATIO[1] * height))

    frame_count = 0
    crossing_events = []

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
                            "track_id": tid,
                            "frame": frame_count,
                            "direction": st.direction,
                            "plate": st.stable_text,
                            "vehicle_type": st.vehicle_type
                        })
                        print(f"[CROSSING] Track {tid} -> {st.direction} (frame {frame_count}, "
                              f"plate={st.stable_text}, type={st.vehicle_type})")

        # ====================================================
        # Vehicle type model (COCO) -- runs less often than plate tracking
        # ====================================================

        if frame_count % config.VEHICLE_DETECT_EVERY == 0:
            vehicle_results = vehicle_model(
                frame, imgsz=config.YOLO_IMGSZ, conf=config.VEHICLE_CONF, verbose=False
            )

            vehicle_detections = []
            for vres in vehicle_results:
                if vres.boxes is None:
                    continue
                for i in range(len(vres.boxes)):
                    cls_id = int(vres.boxes.cls[i].cpu().numpy())
                    if cls_id not in config.COCO_VEHICLE_CLASSES:
                        continue
                    vbox = vres.boxes.xyxy[i].cpu().numpy()
                    class_name = config.COCO_VEHICLE_CLASSES[cls_id]
                    vehicle_detections.append((vbox, class_name))

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

        if frame_count % config.OCR_EVERY == 0:
            for tid, st in tracks.items():
                if st.box is None:
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

            x1, y1, x2, y2 = st.box
            x1 = max(0, min(width - 1, x1))
            y1 = max(0, min(height - 1, y1))
            x2 = max(0, min(width - 1, x2))
            y2 = max(0, min(height - 1, y2))

            if st.stable_text is None:
                box_color = (0, 200, 255)  # yellow/orange = still trying
                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                continue

            box_color = (0, 255, 0)  # green = confirmed
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 3)

            centroid = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            cv2.circle(frame, centroid, 4, (0, 0, 255), -1)

            label = f"ID{tid} | {st.stable_text}"
            if st.vehicle_type:
                label += f" | {st.vehicle_type}"
            if st.direction:
                label += f" | {st.direction}"

            cv2.putText(frame, label, (x1, max(30, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, box_color, 2)

        # ====================================================
        # Top-of-screen summary -- only vehicles with successful OCR
        # ====================================================

        active_texts = [
            f"ID{tid}:{st.stable_text}({st.vehicle_type or '?'},{st.direction or '?'})"
            for tid, st in tracks.items()
            if st.stable_text and frame_count - st.last_seen_frame <= config.DETECT_EVERY * 2
        ]
        summary = " | ".join(active_texts) if active_texts else "Waiting for plate..."

        cv2.rectangle(frame, (15, 15), (min(width - 15, 950), 60), (0, 0, 0), -1)
        cv2.putText(frame, summary[:80], (25, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)

        cv2.putText(frame, f"Frame: {frame_count}", (20, height - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        out.write(frame)
        cv2.imshow("Syrian Plate Recognition - Full Pipeline", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break

    cap.release()
    out.release()
    cv2.destroyAllWindows()

    print("=" * 70)
    print("FINISHED")
    print("Output:", output_path)
    print("Debug folder:", config.DEBUG_FOLDER)
    print(f"Total crossing events: {len(crossing_events)}")
    for ev in crossing_events:
        print(f"  Track {ev['track_id']} | {ev['direction']} | frame {ev['frame']} | "
              f"plate={ev['plate']} | type={ev['vehicle_type']}")
    print("=" * 70)
