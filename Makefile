.PHONY: install run test help

help:
	@echo "API TestGen — Available commands:"
	@echo "  make install   — Create venv and install dependencies"
	@echo "  make run       — Start the FastAPI backend"
	@echo "  make test      — Run unit tests"

install:
	cd backend && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
	@echo ""
	@echo "✓ Done. Now run: make run"

run:
	cd backend && ./venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	cd backend && PYTHONPATH=. ./venv/bin/python ../tests/test_generator.py
