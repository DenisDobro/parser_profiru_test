install:
	pip install -e .[dev]

lint:
	ruff check src tests
	mypy src

test:
	pytest -q

run:
	profiru-watch run --config config.yaml
