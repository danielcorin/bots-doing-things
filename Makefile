.PHONY: compile install venv serve deploy

serve:
	hugo server

deploy:
	modal deploy src/github/commit.py
	modal deploy src/bots/connections.py
	modal deploy src/crons/connections.py

compile:
	uv pip compile requirements.in -o requirements.txt

venv:
	python -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install uv

install: venv
	. .venv/bin/activate && uv pip install -r requirements.txt
