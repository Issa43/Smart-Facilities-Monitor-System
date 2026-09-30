"""Condensed, print-sized pipeline diagrams for the three detection services."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, Polygon

for f in ("times.ttf", "timesbd.ttf"):
    font_manager.fontManager.addfont(f"C:/Windows/Fonts/{f}")
plt.rcParams["font.family"] = "Times New Roman"

FILL, EDGE, TERM_FILL = "#dae8fc", "#6c8ebf", "#f5f5f5"
FS = 9            # prints at 9 pt: figure is inserted at its own width (6.1 in = 15.5 cm)
W = 6.1
SPINE_X, BOX_W, DEC_W = 2.05, 3.5, 3.7
SIDE_X, SIDE_W = 5.05, 1.95
LINE_H, GAP = 0.16, 0.22


def height(kind, text):
    n = text.count("\n") + 1
    return n * LINE_H + (0.34 if kind == "dec" else 0.2)


def draw(steps, path):
    total = sum(height(s["kind"], s["text"]) for s in steps) + GAP * (len(steps) - 1) + 0.2
    fig = plt.figure(figsize=(W + 0.1, total))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W + 0.1); ax.set_ylim(0, total); ax.axis("off")
    y = total - 0.1
    prev_bottom = None
    for s in steps:
        h = height(s["kind"], s["text"]); top, bottom, mid = y, y - h, y - h / 2
        if s["kind"] == "dec":
            hw = DEC_W / 2
            ax.add_patch(Polygon([(SPINE_X, top), (SPINE_X + hw, mid), (SPINE_X, bottom), (SPINE_X - hw, mid)],
                                 closed=True, fc=FILL, ec=EDGE, lw=1))
        else:
            fc = TERM_FILL if s["kind"] == "term" else FILL
            ax.add_patch(FancyBboxPatch((SPINE_X - BOX_W / 2, bottom), BOX_W, h,
                                        boxstyle="round,pad=0,rounding_size=0.08", fc=fc, ec=EDGE, lw=1))
        ax.text(SPINE_X, mid, s["text"], ha="center", va="center", fontsize=FS, linespacing=1.15)
        if prev_bottom is not None:
            ax.annotate("", xy=(SPINE_X, top), xytext=(SPINE_X, prev_bottom),
                        arrowprops=dict(arrowstyle="-|>", color="black", lw=0.9, shrinkA=0, shrinkB=0))
            if s.get("down"):
                ax.text(SPINE_X + 0.07, (top + prev_bottom) / 2, s["down"], fontsize=FS - 0.5,
                        fontweight="bold", va="center")
        if s.get("side"):
            sh = height("proc", s["side"])
            left = SPINE_X + (DEC_W / 2 if s["kind"] == "dec" else BOX_W / 2)
            ax.add_patch(FancyBboxPatch((SIDE_X - SIDE_W / 2, mid - sh / 2), SIDE_W, sh,
                                        boxstyle="round,pad=0,rounding_size=0.06", fc="white", ec=EDGE, lw=0.9, ls="--"))
            ax.text(SIDE_X, mid, s["side"], ha="center", va="center", fontsize=FS - 0.5, linespacing=1.1)
            ax.annotate("", xy=(SIDE_X - SIDE_W / 2, mid), xytext=(left, mid),
                        arrowprops=dict(arrowstyle="-|>", color="black", lw=0.9, shrinkA=0, shrinkB=0))
            ax.text((left + SIDE_X - SIDE_W / 2) / 2, mid + 0.05, s.get("side_label", "No"),
                    ha="center", va="bottom", fontsize=FS - 0.5, fontweight="bold")
        prev_bottom = bottom
        y = bottom - GAP
    fig.savefig(path, dpi=300)
    plt.close(fig)
    print(path, f"{W + 0.1:.1f} x {total:.1f} in")


fire = [
    dict(kind="term", text="Newest frame from the camera\n(RTSP via MediaMTX, reader thread)"),
    dict(kind="dec", text="Model enabled for\nthis camera?", side="Show 'model disabled'\non the live view"),
    dict(kind="dec", text="Every 5th frame?", side="Draw the last known boxes\nand stream the frame", down="Yes"),
    dict(kind="proc", text="YOLO26m detection\n(640 px, confidence ≥ 0.378)", down="Yes"),
    dict(kind="proc", text="Add 1 or 0 to each class window\n(last 6 checks, older than 10 s dropped)"),
    dict(kind="dec", text="Fire ≥ 4 of 6\nor Smoke ≥ 3 of 6?", side="Close the class incident\nafter 30 s without detection"),
    dict(kind="dec", text="Incident already open\nfor this class?", side="Remind only if 5 min passed\nsince the last alarm", side_label="Yes", down="Yes"),
    dict(kind="proc", text="Open the incident and raise an alarm", down="No"),
    dict(kind="proc", text="Snapshot: strongest frame in the window\nwith all boxes of the class"),
    dict(kind="term", text="Save the snapshot to protected storage\nand POST the event to the backend (async)"),
]
intrusion = [
    dict(kind="term", text="Frame from the camera stream\n(read by Ultralytics for tracking)"),
    dict(kind="dec", text="Model enabled and a\nrestricted ROI drawn?", side="Stream the frame\nwithout detection"),
    dict(kind="proc", text="YOLO26n person detection (ONNX, 1280 px)\nconfidence 0.4 by day, 0.2 at night", down="Yes"),
    dict(kind="proc", text="ByteTrack gives each person a track ID"),
    dict(kind="proc", text="Foot point of each person\n(bottom centre of the box)"),
    dict(kind="dec", text="Foot point inside an ROI\nrestricted right now?", side="Count time outside;\nre-arm after 2 s outside"),
    dict(kind="dec", text="Inside for 1 s and\nnot yet alarmed?", side="Keep counting\nthe dwell time", down="Yes"),
    dict(kind="proc", text="Raise the alarm: snapshot with the ROIs\nand the person drawn in red", down="Yes"),
    dict(kind="term", text="POST intrusion_alert to the backend\n(ROI id and entry time); tracks unseen\nfor 10 s are forgotten"),
]
anpr = [
    dict(kind="term", text="Newest frame from the gate camera"),
    dict(kind="dec", text="Model enabled and\nvirtual line drawn?", side="Stream the frame\nwithout detection"),
    dict(kind="proc", text="YOLO26n plate detection (1024 px)\nand ByteTrack on every processed frame", down="Yes"),
    dict(kind="proc", text="Continue split tracks: a new track within\n2 plate widths of one lost ≤ 10 frames ago"),
    dict(kind="proc", text="PaddleOCR on the plate crop\n(one or two rows, deskewed copy)"),
    dict(kind="dec", text="Reading confidence\n≥ 0.85?", side="Reject the reading:\nno read beats a wrong one"),
    dict(kind="proc", text="Parse the format (2+5 or 3+4) and vote\n(confirm at 3 reads, lock at 5)", down="Yes"),
    dict(kind="proc", text="Vehicle type (every 2nd frame): smallest\nCOCO vehicle box around the plate, majority vote"),
    dict(kind="dec", text="Plate crossed the line?\n(other side for 3 detections)", side="Keep tracking"),
    dict(kind="dec", text="Plate confirmed and\nvehicle type known?", side="Crossing waits;\ndropped if the track ends", down="Yes"),
    dict(kind="dec", text="Same plate and direction\nsent in the last 30 s?", side="Ignore the repeat", side_label="Yes", down="Yes"),
    dict(kind="term", text="Check the authorized-vehicle registry, then\nPOST vehicle_entry or vehicle_exit", down="No"),
]
draw(fire, "figures/fire_pipeline_condensed.png")
draw(intrusion, "figures/intrusion_pipeline_condensed.png")
draw(anpr, "figures/anpr_pipeline_condensed.png")
