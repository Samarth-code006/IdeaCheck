.PHONY: env test run demo

env:
	python3 -m pip install -r requirements.txt

test:
	python3 -m pytest -q

run:
	python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

demo:
	NOVELTY_MODE=demo python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000

