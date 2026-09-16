"""
Exercises the plate assembly logic with fabricated OCR detections, so the
layout/format decisions are tested without needing EasyOCR or the weights.

Each case mirrors one of the real photos in Deployment/Photos.
"""
import sys
sys.path.insert(0, ".")
import ocr


def det(text, x1, x2, y1, y2, conf=0.9):
    return {"text": text, "conf": conf,
            "x": (x1 + x2) / 2, "y": (y1 + y2) / 2,
            "x1": x1, "x2": x2, "y1": y1, "y2": y2}


CASES = [
    # name, detections, expected text, expected category
    ("Rectangle.jpg  one row 2+5   '19 [emblem] 13058'",
     [det("19", 10, 60, 20, 80), det("13058", 140, 320, 20, 80)],
     "19-13058", ocr.PERMANENT),

    ("SemiRectangle.jpg  two rows 2+5   '14' / '67232'",
     [det("14", 20, 70, 10, 55), det("67232", 15, 290, 90, 150)],
     "14-67232", ocr.PERMANENT),

    ("Square.jpg  two rows 3+4   '531' / '5950'",
     [det("531", 20, 110, 10, 60), det("5950", 15, 250, 95, 165)],
     "531-5950", ocr.TEMPORARY),

    ("two rows 3+4 NOT starting with 5  '631' / '5950'",
     [det("631", 20, 110, 10, 60), det("5950", 15, 250, 95, 165)],
     "631-5950", ocr.TEMPORARY),

    ("per-digit detections, one row 2+5",
     [det("1", 10, 30, 20, 80), det("9", 32, 52, 20, 80),
      det("1", 140, 160, 20, 80), det("3", 162, 182, 20, 80),
      det("0", 184, 204, 20, 80), det("5", 206, 226, 20, 80),
      det("8", 228, 248, 20, 80)],
     "19-13058", ocr.PERMANENT),

    ("wrong digit count is rejected  '12' / '345'",
     [det("12", 20, 70, 10, 55), det("345", 15, 200, 90, 150)],
     None, None),
]


def main():
    failures = 0

    print("=" * 78)
    print("ASSEMBLY: layout from detections, format from where the split lands")
    print("=" * 78)
    for name, items, want_text, want_cat in CASES:
        text, category, conf = ocr.assemble_plate(items, "auto")
        ok = (text == want_text and category == want_cat)
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        print(f"        got {text!r} / {category!r} conf={conf:.2f}"
              f"   want {want_text!r} / {want_cat!r}")

    print()
    print("=" * 78)
    print("5xx PRIOR: adjusts confidence, never filters")
    print("=" * 78)
    with_5 = ocr.score_pair("531", "5950", 0.80)
    without_5 = ocr.score_pair("631", "5950", 0.80)
    print(f"  '531-5950' -> {with_5[0]!r} conf={with_5[2]:.3f}")
    print(f"  '631-5950' -> {without_5[0]!r} conf={without_5[2]:.3f}")
    ok = (with_5[0] and without_5[0] and with_5[2] > without_5[2])
    failures += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  both kept, 5xx scores higher")

    print()
    print("=" * 78)
    print("LAYOUT HINT: only orders attempts -- real measured plate geometry")
    print("=" * 78)
    measured = [("Rectangle", 170, 45, "one_row"),
                ("SemiRectangle", 145, 74, "two_row"),
                ("Square", 141, 84, "two_row")]
    for name, w, h, want in measured:
        got = ocr.layout_hint(w, h)
        ok = got == want
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name:15} {w}x{h} ratio={w/h:.2f} -> {got} (want {want})")

    print()
    print("=" * 78)
    print("REGRESSION: the old aspect-ratio rule forced Square into 2+5")
    print("=" * 78)
    old = "square" if 141 / 84 < 1.50 else "rectangle"
    old_format = (2, 5) if old == "rectangle" else (3, 4)
    print(f"  old get_plate_type(141, 84) -> {old!r}, format {old_format}  (true format (3, 4))")
    new_text, new_cat, _ = ocr.assemble_plate(CASES[2][1], "auto")
    ok = new_text == "531-5950"
    failures += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  new path reads {new_text!r} as {new_cat!r}")

    print()
    print("ALL TESTS PASSED" if not failures else f"{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
