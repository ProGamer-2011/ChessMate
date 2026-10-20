# ChessMate

ChessMate now includes a **Flutter UI shell** for a single cross-platform frontend codebase (web, Android/iOS, Windows/macOS/Linux), while existing Python chess/vision logic remains the backend.

## Repository layout

- `/frontend_flutter` — Flutter app shell (navigation + backend connectivity)
- `/api_service/server.py` — Python HTTP service exposing ChessMate profile/analysis routes
- Existing Python modules (`board_system`, `coach_mode.py`, `win_mode.py`, `chesscom_sync`, etc.) remain the core backend logic

## Milestone delivered

- Shared Flutter UI entrypoint with navigation tabs:
  - Home
  - Profile
  - Analysis
  - Live
- Backend connectivity from Flutter:
  - `GET /health`
  - `GET /profile`
- Python service endpoints:
  - `GET /health`
  - `GET /profile`
  - `POST /profile`
  - `POST /analysis/run`

## Run backend (Python)

From repository root:

```bash
python api_service/server.py
```

Backend runs on `http://127.0.0.1:8000` by default.

## Run frontend (Flutter)

From repository root:

```bash
cd frontend_flutter
flutter pub get
flutter run -d chrome --dart-define=CHESSMATE_API_BASE_URL=http://127.0.0.1:8000
```

For Android/iOS/desktop targets, run with the matching `flutter run -d <device>` command.

## Notes

- Current Flutter milestone only migrates UI shell/navigation.
- Python services still own analysis/vision/engine responsibilities.
- Next migration steps can move each ChessMate feature (analysis, live board, modes) screen-by-screen into Flutter while keeping backend logic in Python.
