<div align="center">

# 🏗️ Smart Facility Monitoring System (SFMS)

> **An AI-Driven Dual-Phase Computer Vision Solution for Construction Site Safety & Post-Delivery Automated Security.**

[![Python](https://img.shields.io/badge/Python-3.13%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0%2B-ee4c2c?style=for-the-badge&logo=pytorch)](https://pytorch.org/)
[![Django](https://img.shields.io/badge/Django-4.2%2B-092e20?style=for-the-badge&logo=django)](https://www.djangoproject.com/)
[![YOLO](https://img.shields.io/badge/Ultralytics-YOLO-00FFFF?style=for-the-badge)](https://ultralytics.com/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

</div>

---

## 📌 About The Project

The **Smart Facility Monitoring System (SFMS)** is an end-to-end real-time computer vision platform engineered to bridge the operational gap between facility construction management and post-delivery facility operations.

By integrating custom-trained deep learning object detection models (**YOLO**) with a dynamic **Django** web dashboard, SFMS provides continuous automated site surveillance, proactive hazard mitigation, and intelligent perimeter management.

---

## 🎯 Dual-Phase Operations Workflow

### 1. 🚜 Under-Construction Phase

* **Fire & Smoke Hazard Detection:** Early warning detection for uncontained fires or smoke emissions across open construction zones and material storage yards.
* **Perimeter Intrusion Surveillance:** Monitors restricted entry points and off-limits construction areas during off-hours to prevent theft and unauthorized entry.

### 2. 🏢 Post-Delivery (Facility Management) Phase

* **Automatic License Plate Recognition (ALPR):** Streamlined vehicle entry/exit management for tenants, visitors, and service units.
* **Continuous Safety Surveillance:** 24/7 automated fire and smoke detection across residential and commercial indoor/outdoor zones.
* **Real-Time Security Dashboard:** Instant visual and audio alerts pushed directly to security operators via web socket channels.

---

## ✨ Key Features

* 🚀 **High-Throughput Video Pipeline:** Low-latency inference optimized for multi-camera video feed streaming.
* 🔥 **Robust Custom Models:** Custom-trained YOLO model evaluated on a diverse dataset of **11,000+ images**, achieving a **~79.0% mAP@50**.
* 🛡️ **Advanced Data Augmentation:** Trained with Mosaic, Mixup, and HSV color-space adjustments for adaptability under dynamic outdoor lighting, smoke opacity, and environmental noise.
* 🌐 **Centralized Web Dashboard:** Django-backed intuitive portal for active video monitoring, automated incident logging, and security analytics.

---

## 📊 Model Performance Metrics

| Detection Task | Model Architecture | Training Dataset | mAP@50 | Precision | Status |
| --- | --- | --- | --- | --- | --- |
| **Fire & Smoke Detection** | Custom YOLO-Medium | 11,000+ Images | **~79.0%** | **~80.0%** | 🟢 Production Ready |
| **Perimeter Intrusion** | Custom YOLO | Custom Dataset | Operational | High | 🟡 Integration Phase |
| **ALPR System** | YOLO + OCR Pipeline | Custom Dataset | Operational | High | 🟡 Integration Phase |

---

## 💡 System Architecture

```text
[ IP / Live Camera Feeds ] ──► [ OpenCV Video Frame Sampler ]
                                         │
                                         ▼
                     [ YOLO Multi-Task Detection Engine ]
                        ├── Fire & Smoke Detector
                        ├── Perimeter Intrusion Detector
                        └── License Plate Reader (ALPR)
                                         │
                                         ▼
                     [ Django Backend & Web Dashboard ]
                        ├── Live Stream Rendering
                        ├── Incident Event Logging
                        └── Alert Triggering System

```

---

## 📂 Repository Structure

```text
Smart-Facilities-Monitor-System/
├── apps/                     # Django web app modules (dashboard, alerts, feeds)
├── core/                     # Core system settings and configurations
├── models_weights/           # Trained model weights directory (.pt files local)
├── scripts/                  # Computer vision pipelines and inference utilities
│   ├── fire_detection.py
│   ├── intrusion_detection.py
│   └── alpr_pipeline.py
├── static/                   # Frontend assets (CSS, JS, Images)
├── templates/                # HTML templates for security dashboard
├── .gitignore                # Git exclusion file
├── manage.py                 # Django management script
├── requirements.txt          # Python dependencies
└── README.md                 # Project documentation

```

---

## 🛠️ Tech Stack

* **Deep Learning & Computer Vision:** PyTorch, Ultralytics YOLO, OpenCV
* **Backend Framework:** Python, Django
* **Frontend Interface:** HTML5, CSS3, JavaScript, Bootstrap
* **Training & Hardware Infrastructure:** Kaggle GPU Clusters (CUDA)

---

## 🚀 Getting Started

### Prerequisites

* Python 3.10+ installed
* CUDA-enabled GPU (Recommended for real-time video inference)

### 1️⃣ Clone the Repository

```bash
git clone [https://github.com/Issa43/Smart-Facilities-Monitor-System.git](https://github.com/Issa43/Smart-Facilities-Monitor-System.git)
cd Smart-Facilities-Monitor-System

```

### 2️⃣ Create & Activate Virtual Environment

```bash
# On Linux/macOS
python3 -m venv venv
source venv/bin/activate

# On Windows
python -m venv venv
venv\Scripts\activate

```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt

```

### 4️⃣ Run Django Server

```bash
python manage.py migrate
python manage.py runserver

```

Open `http://127.0.0.1:8000/` in your browser to access the security dashboard.

---

## 🗺️ Roadmap

* [x] Train & validate initial Fire & Smoke Detection Model (~79% mAP50).
* [ ] Train Perimeter Intrusion and ALPR detection models.
* [ ] Integrate multi-threaded OpenCV video stream handler into Django.
* [ ] Implement WebSocket connection for real-time web notifications.
* [ ] Deploy Docker containerization for production environments.

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.

```

```
