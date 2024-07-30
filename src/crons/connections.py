import asyncio
import json

from modal import (
    App,
    Cron,
    Function,
)
from datetime import datetime

app = App("crons.connections")
play_game = Function.lookup("bots.connections", "play_game")
create_file = Function.lookup("github.commit", "create_file")
create_files = Function.lookup("github.commit", "create_files")

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
            date=date,
            content=content,
            model=model,
            tags=json.dumps(tags),
        ),
    )


@app.function(schedule=Cron("0 11 * * *"), timeout=120)
async def play_all_connections():
    date = datetime.now().strftime("%Y-%m-%d")
    models = [
        "gpt-4o",
        "gpt-4-turbo",
        "claude-3.5-sonnet",
        "claude-3-opus",
    ]
    files = {}

    async def play_game_with_timeout(model):
        try:
            return await asyncio.wait_for(play_game.remote.aio(model), timeout=90)
        except asyncio.TimeoutError:
            return None

    # Run play_game calls concurrently with timeout
    futures = [play_game_with_timeout(model) for model in models]
    results = await asyncio.gather(*futures)

    for model, content in zip(models, results):
        if content is not None:
            path = f"content/posts/connections/{date}-{model}.md"
            tags = ["connections", model]
            file_content = FILE_TEMPLATE.format(
                date=date,
                content=content,
                model=model,
                tags=json.dumps(tags),
            )
            files[path] = file_content

    if files:
        commit = f"Connections solutions for {date}"
        create_files.remote(REPO, files, commit)
