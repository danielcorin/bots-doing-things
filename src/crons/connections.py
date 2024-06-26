import json
from modal import (
    Cron,
    Function,
    Stub,
)
from datetime import datetime

stub = Stub("crons.connections")
play_game = Function.lookup("bots.connections", "play_game")
create_file = Function.lookup("github.commit", "create_file")

FILE_TEMPLATE = """+++
title = "Connections {model}"
date = {date}
tags = {tags}
+++

```text
{content}
```
"""

REPO = "danielcorin/bots-doing-things"

# runs at 7 am (ET) every day
@stub.function(schedule=Cron("0 11 * * *"), timeout=40)
def play_connections_gpt_4_turbo():
    play_connections("gpt-4-turbo")

# runs at 7 am (ET) every day
@stub.function(schedule=Cron("0 11 * * *"), timeout=60)
def play_connections_claude_3_opus():
    play_connections("claude-3-opus")


def play_connections(model):
    date = datetime.now().strftime("%Y-%m-%d")
    path = f"content/posts/connections/{date}-{model}.md"
    content = play_game.remote(model)
    commit = f"Connections solution by {model} on {date}"
    tags = ["connections", model]
    create_file.remote(
        REPO,
        path,
        commit,
        FILE_TEMPLATE.format(
            date=date, content=content, model=model, tags=json.dumps(tags),
        ),
    )
