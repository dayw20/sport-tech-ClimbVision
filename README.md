# Climb Project

A climbing analysis tool that uses pose estimation and hold detection to track and analyze climbing sessions.

## Prerequisites

- **Python 3.12.x** — MediaPipe does not support Python 3.13 yet
- **Node.js** (v18 or later recommended)

## Backend Setup

```bash
cd backend

# Create and activate a virtual environment
python3.12 -m venv venv
source venv/bin/activate        # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Apply database migrations
python manage.py migrate

# Start the development server (runs on http://127.0.0.1:8000)
python manage.py runserver
```

### Environment Variables (optional)

Create a file at `backend/.env` to configure API keys:

```
OPENAI_API_KEY=your_key_here      # for AI-assisted wall calibration (optional)
```


## Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server (runs on http://localhost:5173)
npm run dev
```

The frontend connects to the backend at `http://127.0.0.1:8000` by default. To change this, create `frontend/.env`:

```
VITE_API_BASE=http://127.0.0.1:8000
```

## Running the App

1. Start the backend (`python manage.py runserver` inside `backend/`)
2. Start the frontend (`npm run dev` inside `frontend/`)
3. Open [http://localhost:5173](http://localhost:5173) in your browser
