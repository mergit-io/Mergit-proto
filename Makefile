.PHONY: dev dev-backend dev-frontend install install-backend install-frontend build reset-db

PYTHON := backend/.venv/bin/python

install: install-backend install-frontend

install-backend:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -r requirements.txt

install-frontend:
	cd frontend && npm install

dev-backend:
	cd backend && .venv/bin/python main.py

dev-frontend:
	cd frontend && npm run dev

dev:
	@echo "Starting backend on :8000 and frontend on :3000..."
	@trap 'kill 0' SIGINT; \
	  (cd backend && .venv/bin/python main.py) & \
	  (cd frontend && npm run dev) & \
	  wait

build:
	cd frontend && npm run build

reset-db:
	rm -f backend/omnibox.db
	@echo "Database reset."
