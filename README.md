# 🏗️ Smart Facility Monitoring System (SFMS)

> **An AI-driven Computer Vision solution for dual-phase facility management: Construction Site Safety & Post-Delivery Automated Security.**

---

## 📌 About The Project

The **Smart Facility Monitoring System (SFMS)** is a comprehensive, real-time surveillance platform designed to bridge the gap between facility construction management and post-delivery operations. 

By integrating modern deep learning architectures (**YOLO**) with a robust **Django** web application, the system delivers automated site monitoring, hazard detection, and access management.

---

## 🎯 Dual-Phase Operations

### 1. 🚜 Under-Construction Phase
* **Fire & Smoke Hazard Detection:** Early warning detection for uncontained fires or smoke in raw material zones and construction floors.
* **Perimeter Intrusion Detection:** Monitors off-limits areas to prevent unauthorized access and theft of equipment during off-hours.

### 2. 🏢 Post-Delivery (Facility Management) Phase
* **Automatic License Plate Recognition (ALPR):** Streamlined vehicle entry/exit tracking for tenants, service vehicles, and visitors.
* **Continuous Safety Surveillance:** 24/7 automated monitoring for fire/smoke in residential/commercial spaces.
* **Smart Alerting System:** Real-time web alerts pushed directly to security operators.

---

## ✨ Key Features

* 🚀 **Real-Time Video Inference:** Low-latency detection pipeline optimized for multi-camera streaming.
* 🔥 **Robust Fire & Smoke Detection:** Custom-trained YOLO model evaluated on a diverse dataset of **11,000+ images**, achieving a **79% mAP50**.
* 🛡️ **Advanced Augmentation:** Trained using Mosaic, Mixup, and HSV color-space adjustments for high adaptability to dynamic lighting and atmospheric conditions.
* 🌐 **Interactive Dashboard:** Django-backed frontend for live video feeds, event logging, and historical analytics.

---

## 🛠️ Tech Stack

* **Computer Vision & AI:** PyTorch, Ultralytics YOLO, OpenCV
* **Backend Framework:** Django (Python)
* **Frontend:** HTML5, CSS3, JavaScript
* **Training Environment:** Kaggle GPU Clusters

---

## 📊 Model Performance

| Task | Architecture | Dataset Size | mAP@50 | Precision |
| :--- | :--- | :--- | :--- | :--- |
| **Fire & Smoke Detection** | YOLO-Medium | 11,000+ images | **~79.0%** | **~80.0%** |
| **Intrusion Detection** | YOLO | Custom Dataset | Operational | High |
| **ALPR System** | YOLO + OCR | Curation | Operational | High |

---

## 💡 System Architecture

```text
[ IP / Live Camera Streams ]
             │
             ▼
[ OpenCV Video Frame Extractor ]
             │
             ▼
[ YOLO Multi-Task Detection Engine ]
   ├── Fire & Smoke Detection
   ├── Perimeter Intrusion Detection
   └── License Plate Recognition (ALPR)
             │
             ▼
[ Django Backend Service & Web Dashboard ]
