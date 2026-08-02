# System Demo & Rehearsal Checklist — Day 23

This document outlines the step-by-step demonstration rehearsal script, test cases, and offline backup procedures for presenting the CVPX Vehicle License Plate Recognition system.

---

## 🎭 Demo Rehearsal Test Scenarios

### Scenario 1: Authoritative Entry Allowed (`AUTHORIZED`)
1. Open Browser to `http://localhost:3000/authorized-vehicles`.
2. Add plate number `MDY 5D-3062` with status `ACTIVE`.
3. Open `http://localhost:3000/recognition`.
4. Upload `blurry-01.jpg` (or car photo containing plate `5D-3062`).
5. Click **Analyze image**.
6. **Expected Outcome:**
   - Decision: **`AUTHORIZED`** (Green banner).
   - Normalized Plate: `5D3062`.
   - Evidence & Log: Recorded privately.
   - History & Dashboard stats incremented.

---

### Scenario 2: Unauthorized Vehicle Entry (`UNAUTHORIZED`)
1. Open Browser to `http://localhost:3000/recognition`.
2. Upload a vehicle image whose plate is NOT in the allowlist.
3. Click **Analyze image**.
4. **Expected Outcome:**
   - Decision: **`UNAUTHORIZED`** (Red banner).
   - Reason Code: `VEHICLE_NOT_FOUND`.
   - Security Alert generated under `/alerts`.

---

### Scenario 3: Non-Plate Image (`MANUAL_REVIEW`)
1. Open Browser to `http://localhost:3000/recognition`.
2. Upload an image with no license plate (e.g. landscape photo).
3. Click **Analyze image**.
4. **Expected Outcome:**
   - Status: **`No plate detected`** (Yellow banner).
   - Guidance: "Manual inspection needed".

---

### Scenario 4: Local Webcam Demonstration
1. Open Terminal and run:
   ```powershell
   backend\.venv\Scripts\python.exe scripts\run_webcam.py --camera 0
   ```
2. Hold up a clear license plate photo in front of the laptop camera.
3. **Expected Outcome:**
   - Live bounding box overlay on camera feed.
   - Real-time FPS & Latency HUD (top-left).
   - Live authorization status overlay.
   - Press **`Q`** key to exit safely.

---

## 📁 Offline Backup & Fallback Procedures

In case of internet failure or cloud server cold start during presentation:

1. **Local Server Fallback:**
   - Backend API: `python -m uvicorn app.main:app` (Runs on `http://127.0.0.1:8000`)
   - Frontend UI: `npm run dev` (Runs on `http://localhost:3000`)
2. **Reproducible Evaluation Script:**
   - Run system evaluator locally:
     ```powershell
     backend\.venv\Scripts\python.exe scripts\evaluate_system.py --input sample-data\evaluation --output artifacts\evaluation
     ```
3. **Pre-generated Artifacts:**
   - Retained evaluation results: [artifacts/evaluation/evaluation_summary.md](file:///d:/CVPX/artifacts/evaluation/evaluation_summary.md)
