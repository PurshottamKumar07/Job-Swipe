# crwlr + JobSwipe 🚀

A modern, high-performance job discovery crawler, SQLite database with FTS5 search, FastAPI backend, and **JobSwipe** — a Next.js 16 + Tailwind CSS frontend designed with a dark purple theme and optimized for both desktop and mobile/Raspberry Pi touchscreens.

---

## 🎨 JobSwipe Features

1. **Dashboard & Overview (`/`)**:
   - Live metrics: Total Crawled Runs, Extracted Jobs, Remote Jobs, Saved Jobs.
   - Quick action shortcuts.
   - "Paste a Job URL and Auto-Fill Details" shortcut.
   - Top hiring companies chips.

2. **Swipe Jobs (`/swipe`)**:
   - Tinder-style career deck interface with smooth transition animations.
   - **Skip (Left)**, **Save (Bookmark)**, and **Apply (Right)** actions.
   - Interactive remote & on-site category filters.

3. **Add Job from URL (`/add-job`)**:
   - Real-time crawling and extraction preview from any direct job link (LinkedIn, Greenhouse, Lever, Ashby, etc.).
   - Instant extraction breakdown: Company, role, location, salary, description, and requirements.

4. **Browse & Search Jobs (`/jobs`)**:
   - Fast full-text search (FTS5) across title, company, description, and location.
   - Remote-only filter, active-only filter, and pagination.

5. **Job Details (`/jobs/[id]`)**:
   - Tabbed view: **Overview**, **Requirements**, **Company**, and **Insights** (crawler metadata).
   - AI Match score & Resume Fit indicators.
   - Sticky / Pi-friendly bottom action bar with 1-click apply and save.

6. **My Applications (`/applications`)**:
   - Application status tracker: *All*, *In Progress*, *Interview*, *Offer*, *Rejected*.
   - Status update dropdown and persistent tracking in local storage.

7. **Saved Jobs (`/saved`)**:
   - Bookmarked jobs board with direct links and 1-click apply.

8. **Profile (`/profile`)**, **Alerts (`/alerts`)**, **Analytics (`/analytics`)**:
   - Skills manager, resume upload mockup, keyword email alert config, and crawler pipeline charts.

---

## 🖥️ Pi-Friendly Optimizations

- **Responsive & Touch First**: All clickable cards and buttons meet the recommended 44px+ tap targets.
- **Collapsible Sidebar**: Automatically toggles into a top bar + overlay drawer on smaller screens or Pi touchscreen displays.
- **Low CPU/Lightweight Footprint**: Zero heavy 3D or physics libraries; pure CSS transitions and hardware-accelerated transforms.
- **Configurable Backend Host**: Easily bind backend to `0.0.0.0:8000` and point `NEXT_PUBLIC_API_URL` to the Pi's local IP.

---

## 🚀 Quick Start Guide

### 1. Start the Backend API (FastAPI)

```bash
# In the repository root
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

The API docs will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

### 2. Start the Frontend (Next.js)

```bash
cd frontend

# Install dependencies (if not already installed)
npm install

# Run development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## ⚙️ Configuration

In `frontend/.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```
*(If running on a Raspberry Pi accessible over your home LAN, replace `localhost` with your Pi's local IP address, e.g. `http://192.168.1.100:8000`).*

