"""Intrusion detection core, shared by the interactive and headless runners.

Person intrusion detection: YOLO26n (person class only) + built-in ByteTrack
(via ultralytics model.track) + polygon zone check + per-track dwell-time
confirmation before alerting.

This module is the detection logic only -- it draws no windows and writes no
files. IntrusionDetection.py in the model folder remains the interactive
runner; headless.py here is the service runner that feeds confirmed
intrusions to the SFLMS backend.

The tuning constants below keep the values measured on the sample footage as
their defaults, and every one can be overridden by an environment variable so
a deployment does not need a code edit.
"""

import os
import time
from collections import defaultdict
from datetime import datetime, timezone

import cv2
import numpy as np
from ultralytics import YOLO


def _env_float(name, default):
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def _env_int(name, default):
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default

# =============================================================
# 1. الإعدادات (Config) — عدّل هذا القسم بحسب الكاميرا والمكان
# =============================================================

MODEL_PATH = "yolo26n.pt"          # مسار أوزان YOLO26n
VIDEO_SOURCE = "Vedio/PeopleWalking.mp4"                   # 0 = الكاميرا المدمجة، أو ضع رابط RTSP/HTTP لكاميرا IP، أو مسار فيديو محلي

PERSON_CLASS_ID = 0                # class 0 = person في COCO
# عتبة الثقة: تُختار تلقائياً حسب إضاءة المشهد.
# كاميرات الرؤية الليلية (IR LED) تُخرج صورة رمادية خافتة، وعندها تسقط نسبة
# الكشف إلى 48% بعتبة 0.4 لكنها ترتفع إلى 79% بعتبة 0.15 (مقاس على محاكاة IR).
# النهار يبقى على 0.4: خفضها نهاراً يضاعف المسارات الوهمية بلا فائدة.
CONF_DAY = _env_float('INTRUSION_CONF_DAY', 0.4)
CONF_NIGHT = _env_float('INTRUSION_CONF_NIGHT', 0.2)
NIGHT_LUMA_THRESHOLD = _env_int('INTRUSION_NIGHT_LUMA', 60)          # متوسط سطوع الإطار (0-255) الذي نعتبر تحته المشهد ليلياً
CONF_THRESHOLD = min(CONF_DAY, CONF_NIGHT)   # ما يُمرَّر للكاشف؛ الترشيح النهائي في الحلقة
# حجم الاستدلال: YOLO يصغّر الإطار إلى مربع بهذا الضلع قبل الكشف.
# مع مصدر 4K يصبح الشخص البعيد (~100 بكسل) نحو 17 بكسل عند 640 فلا يُكشف،
# ومع كل كشف ضائع يفقد المتتبّع المسار ثم يعطيه رقماً جديداً عند عودته.
# مقاس على هذا الفيديو: 640 -> 8.7 شخص/إطار، 1280 -> 16.1 شخص/إطار مقابل 5% زمن إضافي.
IMGSZ = _env_int('INTRUSION_IMGSZ', 1280)
# تخطّي إطارات لتقليل الحمل: يُمرَّر إلى ultralytics كـ vid_stride فيتخطّى القراءة
# والاستدلال معاً. (النسخة السابقة كانت تتجاهل النتائج بعد حساب الاستدلال،
# فلا توفّر شيئاً: 22.3s مقابل 22.1s على نفس الفيديو، مع إهدار ثلثي الكشوفات.)
VID_STRIDE = _env_int('INTRUSION_VID_STRIDE', 1)                     # 1 = كل إطار، 2 = إطار من كل اثنين...

# نقاط منطقة التسلل (polygon) بإحداثيات البكسل — رتّب النقاط بالتسلسل حول المحيط.
# استخدام polygon (وليس rectangle فقط) يسمح بتحديد محيط غير منتظم
# (زاوية مبنى، سياج مائل...) بنفس الكود.
#
# None = المنطقة تغطي كامل إطار الفيديو (يُبنى المضلّع تلقائياً من أبعاد أول إطار،
# فلا حاجة لمعرفة دقة الكاميرا مسبقاً). ضع قائمة نقاط بدل None لتحديد منطقة أضيق، مثال:
#     ZONE_POLYGON = np.array([[150, 100], [450, 100], [450, 350], [150, 350]], dtype=np.int32)
ZONE_POLYGON = None

BOX_CORNER_RATIO = 0.12            # نصف قطر انحناء زوايا الصندوق كنسبة من ضلعه الأقصر
                                   # (نسبة لا قيمة ثابتة، وإلا صار الشخص البعيد كبسولة)
BOX_CORNER_MAX_PX = 18             # حدّ أعلى للانحناء بعد القياس مع دقة الإطار

ZONE_DRAW_MARGIN_PX = 2            # إزاحة الرسم للداخل فقط (كي لا يُقصّ خط المضلّع عند حافة الإطار)
                                   # لا تؤثر على فحص الدخول: المنطقة تبقى كامل الإطار

# العتبات بالثواني لا بالإطارات: عدد الإطارات يعني مدة مختلفة مع كل fps
# (8 إطارات = 0.33s على 24fps لكن 0.13s على 60fps)، وتتغيّر أيضاً مع VID_STRIDE.
# تُحوَّل تلقائياً إلى إطارات عند التشغيل حسب fps المصدر.
DWELL_CONFIRM_SECONDS = _env_float('INTRUSION_DWELL_SECONDS', 0.35)       # كم ثانية يبقى الشخص داخل المنطقة قبل إطلاق التنبيه
STALE_TRACK_TIMEOUT_S = _env_float('INTRUSION_STALE_SECONDS', 10.0)       # بعد كم ثانية من عدم ظهور track id نعتبره خرج ونحذفه من الذاكرة

SAVE_OUTPUT_VIDEO = "intrusion_output.mp4"   # مسار حفظ الفيديو المُعلّم (None لتعطيل الحفظ)
OUTPUT_FPS = None                  # None = خذ fps من الفيديو المصدر (ضع رقماً لفرض قيمة)
FALLBACK_FPS = 25.0                # يُستخدم إذا تعذّرت قراءة fps المصدر (كاميرا/RTSP)

# ---- إعدادات العرض على الشاشة ----
SHOW_WINDOW = True                 # False عند التشغيل على سيرفر بلا شاشة (Docker/headless)
WINDOW_NAME = "Intrusion Detection"
FIT_TO_SCREEN = True               # لائم إطار العرض مع شاشة اللابتوب (لا يؤثر على الفيديو المحفوظ)
SCREEN_FILL_RATIO = 0.92           # نسبة مساحة الشاشة التي تشغلها النافذة (اترك هامشاً لشريط المهام)
START_FULLSCREEN = False           # ابدأ بملء الشاشة (مفتاح f يبدّل الوضع أثناء التشغيل)

# إعداد متتبّع محلي بدل bytetrack.yaml الافتراضي: يرفع track_buffer من 30 إلى 90
# إطاراً ليحتفظ بهوية من يختفي خلف العمود. انظر الملف للتفاصيل والقياسات.
TRACKER_CFG = "bytetrack_sfms.yaml"


# =============================================================
# 2. دوال مساعدة (Helpers)
# =============================================================

def foot_point(xyxy, frame_shape=None):
    """
    نقطة منتصف أسفل صندوق الكشف (موضع القدمين تقريباً) — أدق من مركز الصندوق
    لفحص الموقع على مستوى الأرض، خصوصاً مع زاوية كاميرا مائلة للأسفل.

    frame_shape: لحصر النقطة داخل حدود الإطار. ضروري لأن YOLO يقصّ الصندوق عند
    حافة الصورة فتصبح y2 = height تماماً، أي خارج المضلّع بفارق بكسل واحد —
    وهذا كان يُسقط أشخاصاً واقفين عند أسفل الكادر من المنطقة ويكرّر تنبيههم.
    """
    x1, y1, x2, y2 = xyxy
    x, y = int((x1 + x2) / 2), int(y2)
    if frame_shape is not None:
        h, w = frame_shape[:2]
        x = min(max(x, 0), w - 1)
        y = min(max(y, 0), h - 1)
    return (x, y)


def full_frame_polygon(width, height):
    """مضلّع مستطيل يغطي كامل إطار الفيديو (كل بكسل داخل المنطقة)."""
    x2, y2 = width - 1, height - 1
    return np.array([[0, 0], [x2, 0], [x2, y2], [0, y2]], dtype=np.int32)


def get_screen_size(default=(1920, 1080)):
    """أبعاد شاشة اللابتوب بالبكسل الحقيقي (مع مراعاة تكبير العرض في ويندوز)."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()          # وإلا أعاد ويندوز أبعاداً مصغّرة عند تكبير 125%/150%
        w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    try:                                     # لينكس/ماك
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return w, h
    except Exception:
        return default


def fit_frame_to_screen(frame, screen_wh, ratio=SCREEN_FILL_RATIO):
    """
    نسخة من الإطار مقيسة لتملأ الشاشة مع الحفاظ على نسبة الأبعاد.
    مهم مع مصدر 4K على شاشة 1080p: بدونها تفتح النافذة بضعف حجم الشاشة وتُقصّ حوافها.
    """
    h, w = frame.shape[:2]
    screen_w, screen_h = screen_wh
    scale = min(screen_w * ratio / w, screen_h * ratio / h)
    if abs(scale - 1.0) < 0.01:
        return frame, 1.0
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    # INTER_AREA أفضل للتصغير، INTER_LINEAR أسرع للتكبير
    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    return cv2.resize(frame, new_size, interpolation=interp), scale


def source_fps(source, fallback=FALLBACK_FPS):
    """
    fps الفيديو المصدر — يُستعمل لتحويل العتبات الزمنية إلى إطارات.

    لا يقرأ OUTPUT_FPS: ذاك إعداد إخراج فقط، وخلطه هنا كان يغيّر سلوك الكشف
    نفسه (OUTPUT_FPS=10 كان يجعل عتبة المكوث 4 إطارات بدل 8 فترتفع التنبيهات
    من 23 إلى 27 دون أن يمسّ المستخدم أي إعداد كشف).

    يُفحص ملفات الفيديو فقط: فتح VideoCapture على كاميرا (0) أو رابط RTSP هنا
    يعني فتح المصدر مرة ثانية بالتوازي مع ultralytics — وهذا يفشل أو يحجز
    الكاميرا على ويندوز. للمصادر الحيّة نستخدم القيمة الاحتياطية مباشرة.
    """
    if not (isinstance(source, str) and os.path.isfile(source)):
        return float(fallback)
    cap = None
    try:
        cap = cv2.VideoCapture(source)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps and 0 < fps < 240:
            return float(fps)
    except Exception:
        pass
    finally:
        if cap is not None:
            cap.release()
    return float(fallback)


def apply_fullscreen(name, on):
    cv2.setWindowProperty(name, cv2.WND_PROP_FULLSCREEN,
                          cv2.WINDOW_FULLSCREEN if on else cv2.WINDOW_NORMAL)


def window_closed(name):
    """هل أغلق المستخدم النافذة بزر X؟ بدون هذا الفحص تستمر الحلقة وتُعيد فتحها."""
    try:
        return cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


def pause_until_key(name):
    """
    إيقاف مؤقت للفحص: مسافة للاستئناف، q/Esc للخروج، وإغلاق النافذة يُنهي أيضاً.
    (النسخة السابقة كانت تنتظر المسافة فقط، فيعلق البرنامج إن أردت الخروج أثناء الإيقاف.)
    """
    while True:
        k = cv2.waitKey(50) & 0xFF
        if k in (ord(' '), ord('q'), 27):
            return k
        if window_closed(name):
            return ord('q')


def frame_is_dark(frame, threshold=NIGHT_LUMA_THRESHOLD):
    """
    هل المشهد ليلي؟ متوسط السطوع على نسخة مصغّرة (رخيص: ~0.1ms على إطار 4K).
    يُستخدم لاختيار عتبة الثقة، فالكاميرا نفسها قد تنتقل بين نهار وليل أثناء التشغيل.
    """
    small = cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA)
    return float(small.mean()) < threshold


def is_inside_zone(point, polygon):
    return cv2.pointPolygonTest(polygon, point, False) >= 0


def raise_alert(person_no, point, track_id):
    """
    نقطة التوسع: هنا تضع كود إرسال إيميل / صوت تنبيه / طلب REST API إلى الباكند
    (نفس النمط المستخدم في المكونات الأخرى: POST + PATCH لحدث التسلل).

    person_no: الرقم المعروض على الشاشة (متسلسل ومقروء)
    track_id : رقم ByteTrack الداخلي — احتفظ به للربط مع سجلّات المتتبّع
    """
    print(f"[ALERT] Intrusion confirmed — person P{person_no} (track {track_id}) at {point} "
          f"({time.strftime('%Y-%m-%d %H:%M:%S')})")


class TrackState:
    """
    يتتبّع حالة كل شخص (track id): كم إطار متتالي داخل المنطقة، وهل تم التنبيه له، وآخر ظهور له.

    العتبات تُمرَّر بالإطارات بعد تحويلها من الثواني حسب fps الفعلي.
    آخر ظهور يُقاس برقم الإطار لا بساعة الجدار: معالجة فيديو مسجّل تجري بسرعة
    تختلف عن سرعة تشغيله (هنا ~12 إطار/ث مقابل 24)، فساعة الجدار كانت تحذف
    المسارات بعد مدة فيديو مختلفة تماماً عن المقصود.
    """

    def __init__(self, dwell_frames, stale_frames, on_alert=None):
        # on_alert lets the caller replace the print with real delivery
        # (the headless runner POSTs to SFLMS). Signature matches raise_alert
        # plus the track's last box, which the backend needs as bbox.
        self.on_alert = on_alert or (
            lambda person_no, point, track_id, xyxy, conf, entered_at:
            raise_alert(person_no, point, track_id)
        )
        self.dwell_frames = max(1, int(dwell_frames))
        self.stale_frames = max(1, int(stale_frames))
        self.dwell_count = defaultdict(int)
        self.alerted = set()
        self.last_seen = {}
        # Wall-clock moment each track entered the zone. The dwell counter is
        # in frames, but the backend wants a timestamp on every intrusion
        # event, and it must be the entry instant -- not the confirmation.
        self.entered_at = {}
        # رقم عرض متسلسل لكل مسار. رقم ByteTrack الداخلي عدّاد عام يزداد مع كل
        # مسار مرشّح حتى لو حُذف بعد إطار واحد، فتظهر فجوات ويقفز الرقم بعيداً
        # عن عدد الأشخاص الفعلي (هنا: 37 رقماً ظاهراً بينما بلغ العدّاد 65).
        self.display_id = {}
        self._next_display = 1

    def display_for(self, track_id):
        if track_id not in self.display_id:
            self.display_id[track_id] = self._next_display
            self._next_display += 1
        return self.display_id[track_id]

    def update(self, track_id, inside, point, frame_idx, xyxy=None, conf=None):
        self.last_seen[track_id] = frame_idx

        if inside:
            if self.dwell_count[track_id] == 0:
                self.entered_at[track_id] = datetime.now(timezone.utc)
            self.dwell_count[track_id] += 1
            if self.dwell_count[track_id] >= self.dwell_frames and track_id not in self.alerted:
                self.on_alert(self.display_for(track_id), point, track_id, xyxy, conf,
                              self.entered_at.get(track_id))
                self.alerted.add(track_id)
        else:
            # خرج من المنطقة: صفّر العداد واسمح بتنبيه جديد إذا عاد لاحقاً
            self.dwell_count[track_id] = 0
            self.alerted.discard(track_id)
            self.entered_at.pop(track_id, None)

    def prune_stale(self, frame_idx):
        stale_ids = [tid for tid, seen in self.last_seen.items()
                     if frame_idx - seen > self.stale_frames]
        for tid in stale_ids:
            self.last_seen.pop(tid, None)
            self.dwell_count.pop(tid, None)
            self.alerted.discard(tid)
            self.entered_at.pop(tid, None)
            # لا تنسَ جدول أرقام العرض: بدون حذفه ينمو بلا حدود في تشغيل
            # كاميرا متواصل (مقاس: 500 مسار قصير -> 500 مدخلاً بينما بقيت
            # بقية الجداول عند 6). الرقم نفسه لا يُعاد استخدامه.
            self.display_id.pop(tid, None)


def draw_rounded_rect(img, x1, y1, x2, y2, color, thickness, radius):
    """
    مستطيل بزوايا دائرية: أربعة أضلاع مستقيمة + أربعة أرباع دوائر عند الزوايا.
    نصف القطر يُقصّ إلى نصف أصغر ضلع كي لا تتشوّه الصناديق الضيقة (شخص بعيد).
    """
    r = int(max(1, min(radius, (x2 - x1) // 2, (y2 - y1) // 2)))

    cv2.line(img, (x1 + r, y1), (x2 - r, y1), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x1 + r, y2), (x2 - r, y2), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x1, y1 + r), (x1, y2 - r), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x2, y1 + r), (x2, y2 - r), color, thickness, cv2.LINE_AA)

    # الزاوية = ربع قطع ناقص؛ الوسيط angle يدوّر الربع إلى موضعه الصحيح
    for (cx, cy, ang) in ((x1 + r, y1 + r, 180), (x2 - r, y1 + r, 270),
                          (x2 - r, y2 - r, 0),   (x1 + r, y2 - r, 90)):
        cv2.ellipse(img, (cx, cy), (r, r), ang, 0, 90, color, thickness, cv2.LINE_AA)


def draw_overlay(frame, zones, boxes_info):
    """zones: list of (label, polygon) -- every ROI drawn for the camera."""
    h, w = frame.shape[:2]
    # الرسم يُقاس مع دقة الإطار: سماكة 2 بكسل تكاد لا تُرى على إطار 4K
    k = max(1.0, h / 720.0)
    line_t = int(round(2 * k))
    font_s = 0.6 * k
    dot_r = int(round(5 * k))

    # إزاحة نقاط الرسم للداخل فقط، وإلا اختفى نصف سماكة الخط خارج حدود الإطار
    m = max(ZONE_DRAW_MARGIN_PX, line_t // 2)
    for label, polygon in zones:
        draw_poly = np.clip(polygon, [m, m], [w - 1 - m, h - 1 - m]).astype(np.int32)
        cv2.polylines(frame, [draw_poly], isClosed=True, color=(255, 0, 0), thickness=line_t)

        # النص أسفل أول نقطة كي يبقى ظاهراً حتى لو كانت المنطقة ملاصقة لحافة الإطار
        label_x, label_y = draw_poly[0]
        cv2.putText(frame, label,
                    (int(label_x) + int(6 * k), int(label_y) + int(22 * k)),
                    cv2.FONT_HERSHEY_SIMPLEX, font_s, (255, 0, 0), line_t)

    max_radius = BOX_CORNER_MAX_PX * k
    for track_id, point, inside, dwell, confirmed, xyxy in boxes_info:
        color = (0, 0, 255) if confirmed else ((0, 255, 255) if inside else (0, 255, 0))

        x1, y1, x2, y2 = (int(v) for v in xyxy)
        x1 = min(max(x1, 0), w - 1); x2 = min(max(x2, 0), w - 1)
        y1 = min(max(y1, 0), h - 1); y2 = min(max(y2, 0), h - 1)
        if x2 > x1 and y2 > y1:
            # الانحناء نسبةً لحجم الصندوق: قيمة ثابتة تجعل الصناديق الضيقة كبسولات
            radius = min(BOX_CORNER_RATIO * min(x2 - x1, y2 - y1), max_radius)
            draw_rounded_rect(frame, x1, y1, x2, y2, color, line_t, radius)

        # نقطة القدمين تبقى ظاهرة: هي النقطة التي يُفحص وجودها داخل المنطقة
        cv2.circle(frame, point, dot_r, color, -1)

        # الرقم فوق الصندوق لا عند القدمين: أوضح نسبةً للجسد وأقل تداخلاً في الزحام
        label = f"P{track_id}" if not inside else f"P{track_id} d={dwell}"
        ty = y1 - int(6 * k)
        if ty < int(18 * k):            # صندوق ملاصق لأعلى الإطار: انقل النص للداخل
            ty = y1 + int(20 * k)
        cv2.putText(frame, label, (x1, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5 * k, color, line_t, cv2.LINE_AA)

    return frame


def draw_hud(frame, text):
    """سطر حالة أسفل الإطار (رقم الإطار/عدد الأشخاص/الحجم) — يفيد أثناء التنقيح."""
    h, w = frame.shape[:2]
    k = max(1.0, h / 720.0)
    org = (int(10 * k), h - int(12 * k))
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX,
                0.5 * k, (0, 0, 0), int(round(4 * k)), cv2.LINE_AA)
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX,
                0.5 * k, (255, 255, 255), int(round(1 * k)), cv2.LINE_AA)
    return frame


# =============================================================
# 3. الحلقة الرئيسية (Main loop)
# =============================================================
