# Expedia Lite

Assignment 1 uses a Vue frontend, FastAPI backend, and persistent SQLite database.

## SQLite setup and run commands

The database is `data/expedia_lite.sqlite3`. FastAPI creates its schema and seeds the supplied CSV records only once; later starts do not reload or duplicate them.

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The default API/docs URLs are `http://127.0.0.1:8000` and `http://127.0.0.1:8000/docs`.

```powershell
Set-Location frontend
npm run dev
```

Vite proxies `/api` to port 8000 by default. To use another local backend port for verification, set `VITE_API_TARGET` before starting Vite.

## Part 2 actions

- SQLite hotel and stay search.
- Booking creation with backend-generated IDs.
- Booking history, including cancelled records.
- Cancellation without deletion.
- Deletion only for an explicitly created test booking.
