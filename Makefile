.PHONY: dev test eval up

AI ?= off

frontend/node_modules: frontend/package-lock.json
	cd frontend && npm ci
	@touch $@

## API with reload on :8000 and the Vite dev server on :5173 (open http://localhost:5173).
## Data (database, uploads, page images) goes to ./data, the folder Docker mounts.
dev: frontend/node_modules
	@trap 'kill 0' EXIT INT TERM; \
	(cd backend && DATA_DIR=$(CURDIR)/data uv run uvicorn --factory pharma_dates.api:create_app --reload --port 8000) & \
	(cd frontend && npm run dev) & \
	wait

## Backend and frontend unit tests.
test: frontend/node_modules
	cd backend && uv run pytest -q
	cd frontend && npm test

## Fetch the public evaluation documents and score the pipeline (AI=on needs credentials in .env).
eval:
	uv run --project backend python eval/fetch.py
	uv run --project backend python eval/run_eval.py --ai $(AI)

## Build the image and run the app at http://localhost:8000.
up:
	mkdir -p data
	docker compose up --build
