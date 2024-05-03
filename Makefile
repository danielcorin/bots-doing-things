.PHONY: serve

serve:
	hugo server

deploy:
	modal deploy src/github/commit.py
	modal deploy src/bots/connections.py
	modal deploy src/crons/connections.py
