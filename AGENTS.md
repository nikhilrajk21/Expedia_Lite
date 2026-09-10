# Expedia Lite Project Rules

- Treat this directory as the project root; never create a nested project directory.
- Keep the Vue frontend and FastAPI/Python backend in `frontend/` and `backend/`, respectively.
- Work Part 1 (CSV search) before implementing any Part 2 SQLite functionality.
- Use only supplied CSV files and supplied database records. Do not invent replacement data.
- Preserve supplied IDs. New records must receive unique IDs.
- Before adding a dependency, follow and document: CHECK, TAKE ACTION, VERIFY.
- Route all application actions through Vue, FastAPI, and Python/SQLite as applicable.
- Keep cancelled bookings in history; deletion is limited to test bookings.
- Record changed files, commands run, verification evidence, limitations, and the next task in `handoffs/current.md`.
- Do not state that a check passed unless it was actually run.
