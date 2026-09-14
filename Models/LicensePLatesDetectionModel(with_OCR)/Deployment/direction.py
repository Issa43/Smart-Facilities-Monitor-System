import config


def side_of_line(point, p1, p2):
    x, y = point
    x1, y1 = p1
    x2, y2 = p2
    cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
    return 1 if cross > 0 else -1


def update_direction(st, centroid, p1, p2, frame_count):
    new_side = side_of_line(centroid, p1, p2)

    if st.current_side is None:
        st.current_side = new_side
        return False

    if new_side == st.current_side:
        st.pending_side = None
        st.pending_count = 0
        return False

    if st.pending_side == new_side:
        st.pending_count += 1
    else:
        st.pending_side = new_side
        st.pending_count = 1

    if st.pending_count >= config.CROSSING_CONFIRM_FRAMES:
        direction_label = config.SIDE_POSITIVE_LABEL if new_side == 1 else config.SIDE_NEGATIVE_LABEL
        st.direction = direction_label
        st.current_side = new_side
        st.pending_side = None
        st.pending_count = 0
        return True

    return False
