# Frontend

React + Vite UI for Kontext Agent.

## Stack

- React 19
- Vite 7
- Tailwind CSS 4
- Axios
- React Router

## Run

```bash
npm install
npm run dev
```

Default URL: `http://localhost:5173`

## Environment Variables

Set in `frontend/.env` or shell:

- `VITE_API_BASE_URL` (default: `http://localhost:8000`)
- `VITE_WS_URL` (default: `ws://localhost:8000`)

## Build

```bash
npm run build
npm run preview
```

## Main Pages

- `src/pages/MeetingPage.jsx`: meeting transcription and summaries
- `src/pages/ChatPage.jsx`: chat and document upload
- `src/pages/LoginPage.jsx`, `src/pages/SignupPage.jsx`: auth
