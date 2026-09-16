"""
Exercises ocr_paddle's parsing and deskew with fabricated recognizer output, so
the logic is tested without PaddleOCR or the weights.

Every read below is what the recognizer actually returned on a TestingOCR photo.
"""
import sys
sys.path.insert(0, ".")

import cv2
import numpy as np

import ocr_paddle as op


ONE_ROW = [
    # name, (text, score), expected plate or None
    ("flag read as '=' splits the groups", ("65=12377", 0.99), "65-12377"),
    ("unsplit 7 digits -> 2+5", ("1850786", 0.99), "18-50786"),
    ("right border read as an 8th digit", ("17572141", 0.85), None),
    ("two-row plate read whole: only the bottom row", ("7467", 0.97), None),
]

TWO_ROWS = [
    # name, (top text, top score, bottom text, bottom score), expected plate or None
    ("3+4 clean", ("551", 1.0, "7467", 1.0), "551-7467"),
    ("2+5 two-row", ("12", 0.83, "47855", 1.0), "12-47855"),
    ("5xx prior picks the window, not position", ("6531", 0.73, "4517", 1.0), "531-4517"),
    ("top row too short", ("2", 0.62, "47855", 1.0), None),
    ("bottom row is not a group length", ("549", 1.0, "65=12377", 0.9), None),
]


def check(ok, message):
    print(f"{'PASS' if ok else 'FAIL'}  {message}")
    return not ok


def rotated_plate(angle):
    """A light plate with a dark border and two dark text bars, tilted by `angle`."""
    image = np.full((260, 360, 3), 90, np.uint8)
    plate = np.full((110, 240, 3), 235, np.uint8)
    cv2.rectangle(plate, (2, 2), (237, 107), (20, 20, 20), 3)
    cv2.rectangle(plate, (20, 18), (100, 40), (20, 20, 20), -1)
    cv2.rectangle(plate, (20, 55), (220, 95), (20, 20, 20), -1)
    image[75:185, 60:300] = plate
    matrix = cv2.getRotationMatrix2D((180, 130), -angle, 1.0)
    return cv2.warpAffine(image, matrix, (360, 260), borderValue=(90, 90, 90))


def main():
    failures = 0

    print("=" * 78)
    print("ONE ROW: whole-plate read")
    print("=" * 78)
    for name, read, want in ONE_ROW:
        got = op.parse_one_row(*read)
        failures += check((got[0] if got else None) == want, f"{name}: {read[0]!r} -> {got}")

    print()
    print("=" * 78)
    print("TWO ROWS: bottom row length picks the format")
    print("=" * 78)
    for name, reads, want in TWO_ROWS:
        got = op.parse_two_rows(*reads)
        failures += check((got[0] if got else None) == want, f"{name}: {reads} -> {got}")

    print()
    print("=" * 78)
    print("CONFIDENCE: contradicting rows and the 5xx prior cost confidence")
    print("=" * 78)
    # Blurry plate 5134310: top "333" (a 3+4 group) over bottom "14310" (a 2+5 group).
    text, conf = op.parse_two_rows("333", 0.98, "14310", 0.95)
    failures += check(conf < op.MIN_ACCEPT_CONF,
                      f"contradicting rows {text!r} conf={conf:.2f} is rejected (< {op.MIN_ACCEPT_CONF})")
    # 6119151: top "611" over "19151" -- the right answer, but still a guess.
    text, conf = op.parse_two_rows("611", 0.92, "19151", 0.97)
    failures += check(text == "61-19151" and conf < 0.92,
                      f"trimmed top row {text!r} keeps the read at lower conf={conf:.2f}")
    with_5 = op.parse_one_row("531=5950", 0.9)[1]
    without_5 = op.parse_one_row("631=5950", 0.9)[1]
    failures += check(without_5 < with_5 == 0.9,
                      f"3+4 not starting with 5 penalised ({without_5:.3f} < {with_5:.3f}), never boosted")

    print()
    print("=" * 78)
    print("DESKEW: estimated angle levels the plate")
    print("=" * 78)
    for angle in (-20, -8, 0, 12, 25):
        image = rotated_plate(angle)
        estimate = op.estimate_skew(image)
        level = op.estimate_skew(op.deskew(image, estimate)) if abs(estimate) >= 1 else estimate
        failures += check(abs(estimate - angle) <= 2 and abs(level) <= 2,
                          f"tilt {angle:+3} -> estimated {estimate:+.1f}, after deskew {level:+.1f}")

    print()
    print("ALL TESTS PASSED" if not failures else f"{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
