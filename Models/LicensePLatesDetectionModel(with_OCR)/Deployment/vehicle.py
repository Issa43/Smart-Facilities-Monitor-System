def simplify_vehicle_type(coco_class_name):
    if coco_class_name in ("truck", "bus"):
        return "Truck"
    elif coco_class_name in ("car", "motorcycle"):
        return "CAR"
    return "Unknown"


def match_vehicle_to_plate(plate_box, vehicle_detections):
    """
    Finds the best-matching vehicle for a given plate by checking whether
    the plate's center falls inside the vehicle's box, preferring the
    smallest matching box (tighter, more accurate association).
    """
    px1, py1, px2, py2 = plate_box
    plate_cx = (px1 + px2) / 2
    plate_cy = (py1 + py2) / 2

    best_match = None
    best_area = float("inf")

    for vbox, vclass_name in vehicle_detections:
        vx1, vy1, vx2, vy2 = vbox

        margin_x = (vx2 - vx1) * 0.1
        margin_y = (vy2 - vy1) * 0.1

        if (vx1 - margin_x <= plate_cx <= vx2 + margin_x and
                vy1 - margin_y <= plate_cy <= vy2 + margin_y):

            area = (vx2 - vx1) * (vy2 - vy1)
            if area < best_area:
                best_area = area
                best_match = vclass_name

    return best_match
