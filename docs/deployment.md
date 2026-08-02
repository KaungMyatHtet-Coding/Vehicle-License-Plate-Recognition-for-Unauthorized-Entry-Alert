# Free-Tier Deployment Guide — Day 19

This guide provides step-by-step instructions for deploying the CVPX system to free-tier cloud platforms without exposing credentials.

---

## 🏗️ Architecture

| Component | Platform | Free Tier Spec |
|---|---|---|
| **Backend API** | [Render](https://render.com) | Docker Web Service (512 MB RAM, 0.1 CPU) |
| **Frontend UI** | [Vercel](https://vercel.com) | Next.js App Router (Global Edge CDN) |
| **Database & Storage** | [Supabase](https://supabase.com) | PostgreSQL 500MB + 1GB Storage |

---

## 1. Supabase Setup (Database & Storage)

### Step 1: Create Project
1. Log in to [Supabase Console](https://supabase.com/dashboard).
2. Create a new project named `cvpx-production`.
3. Save your Database Password securely.

### Step 2: Run SQL Migration
1. Go to **SQL Editor** in Supabase Console.
2. Open `supabase/migrations/20260802000000_initial_schema.sql`.
3. Copy the script content and click **Run**.
4. Verify that tables `authorized_vehicles`, `detection_logs`, and `recognition_activity` are created.

### Step 3: Create Private Evidence Storage Bucket
1. Go to **Storage** → **New Bucket**.
2. Name: `detection-evidence`.
3. Set Public: **OFF (Private)**.
4. Restrict file uploads to `image/jpeg`.

---

## 2. Render Setup (Backend API)

### Step 1: Deploy Web Service
1. Log in to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** → **Web Service**.
3. Connect your GitHub repository `Vehicle-License-Plate-Recognition-for-Unauthorized-Entry-Alert`.
4. Render will auto-detect `render.yaml` or set manually:
   - **Runtime:** `Docker`
   - **Dockerfile Path:** `backend/Dockerfile`
   - **Instance Type:** `Free`

### Step 2: Environment Variables
Add the following in Render **Environment** tab:

```ini
APP_ENV=production
LOG_LEVEL=INFO
FRONTEND_ORIGINS=https://cvpx-frontend.vercel.app,http://localhost:3000
DETECTOR_MODEL_PATH=models/day4/best.onnx
DETECTOR_CONFIDENCE_THRESHOLD=0.15
OCR_MIN_CONFIDENCE=0.80
DECISION_MIN_CONFIDENCE=0.80
```

### Step 3: Verify Health Endpoint
Once deployed, verify:
```bash
curl https://cvpx-backend.onrender.com/health
```
Expected response: `{"status":"ok","service":"vehicle-license-backend","version":"0.1.0"}`

> **Note on Cold-Starts:** Render Free Tier spins down after 15 minutes of inactivity. First request takes ~45-50s to start up. The frontend UI displays a cold-start status banner during wake-up.

---

## 3. Vercel Setup (Frontend UI)

### Step 1: Import Project
1. Log in to [Vercel Dashboard](https://vercel.com/dashboard).
2. Click **Add New...** → **Project**.
3. Import your GitHub repository.
4. Set **Root Directory** to `frontend`.

### Step 2: Environment Variable
Add the following in Vercel **Environment Variables**:

```ini
NEXT_PUBLIC_API_URL=https://cvpx-backend.onrender.com
```

### Step 3: Deploy
Click **Deploy**. Vercel will build the Next.js application and deploy to Edge CDN.

---

## 4. Verification Checklist

- [ ] Health endpoint returns HTTP 200: `curl https://<backend-url>/health`
- [ ] Swagger API docs available: `https://<backend-url>/docs`
- [ ] Frontend loads cleanly without CORS errors
- [ ] Image upload via `/recognition` returns authorization decision
- [ ] Authorized vehicle management via `/authorized-vehicles` works
- [ ] No secrets, API keys, or private database URIs committed to repository
