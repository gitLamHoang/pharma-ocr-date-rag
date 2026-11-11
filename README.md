# Pharma Date Extraction

A date-extraction and review app for pharmaceutical quality teams: upload an English PDF or scan, get every date on it with its meaning, its location on the page and consistency checks, then confirm or correct each one.

**Status: rebuild in progress.** The earlier prototype has been removed. The backend skeleton and date rules live in `backend/`; the app, packaging and full documentation are still being built.

## Development

```bash
cd backend
uv sync
uv run pytest -q
```

## License

MIT. See [LICENSE](LICENSE).
