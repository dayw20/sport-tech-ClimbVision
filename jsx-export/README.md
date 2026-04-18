# ClimbVision Frontend — JSX export

Drop-in React + Vite frontend for the ClimbVision backend.

## Install

Copy the contents of this folder over your existing `frontend/` directory (or into a fresh `npm create vite@latest` scaffold).

```
frontend/
├── index.html
└── src/
    ├── main.jsx
    ├── App.jsx
    ├── App.css
    ├── index.css
    ├── components/
    │   ├── Btn.jsx
    │   ├── CalibrationModal.jsx
    │   ├── Icon.jsx
    │   ├── ModelCard.jsx
    │   ├── ParamInput.jsx
    │   ├── Stat.jsx
    │   ├── StatusPill.jsx
    │   ├── Stepper.jsx
    │   └── ViewTabs.jsx
    └── styles/
        └── tokens.js
```

## Run

```
npm install
npm run dev
```

Set the backend URL in `.env`:

```
VITE_API_BASE=http://127.0.0.1:8000
```

## API endpoints used

All match the existing Django backend:

- `POST /api/jobs/` — upload video
- `POST /api/jobs/{id}/reference-frame/` — generate reference frame (auto-calibrate)
- `POST /api/jobs/{id}/reference-quad/` — save manual 4-corner calibration
- `POST /api/jobs/{id}/projected-holds/` — hold detection
- `POST /api/jobs/{id}/pose-trajectory/` — pose tracking
- `POST /api/jobs/{id}/combine/` — combine (accepts `radius_px`, `min_consecutive_frames`)

## Architecture

| File | Role |
|---|---|
| `App.jsx` | State machine, API calls, orchestrates panels |
| `components/Stepper.jsx` | 4-step progress indicator at top |
| `components/CalibrationModal.jsx` | 4-corner picker with rectified preview |
| `components/ModelCard.jsx` | Hold-detection / pose-tracking run cards |
| `components/ViewTabs.jsx` | Result-view switcher (6 views) |
| `components/ParamInput.jsx` | Combine params (min frames, radius) |
| `components/Stat.jsx` | Metric chip |
| `components/StatusPill.jsx` | Tiny status badge + spinner |
| `components/Btn.jsx` | Shared button |
| `components/Icon.jsx` | Geometric SVG icons (no emoji) |
| `styles/tokens.js` | Shared inline-style tokens |
| `index.css` | Design tokens (CSS vars) + fonts |
| `App.css` | Layout classes |

## Design tokens

All colors are defined in `index.css` as CSS custom properties. Change the accent in one place:

```css
--accent: oklch(0.62 0.16 45);  /* terracotta — swap hue (45) for any sport accent */
```
