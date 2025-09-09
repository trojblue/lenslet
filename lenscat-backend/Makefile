.PHONY: dev worker fmt

dev:
	uvicorn src.lenscat_backend.main:app --reload --host 127.0.0.1 --port 7070

worker:
	python -m src.lenscat_backend.workers.run_worker

fmt:
	ruff check --fix src || true
	black src || true
