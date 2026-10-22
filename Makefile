.PHONY: install dashboard test lint all

install:
	pip install -r requirements.txt

dashboard:
	PYTHONPATH=. python examples/dashboard.py

test:
	python -m unittest discover -s tests -t . -v

lint:
	ruff check .

all: lint test dashboard
