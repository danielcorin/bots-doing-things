import os
from collections import defaultdict
from datetime import datetime


class ModelStats:
    def __init__(self):
        self.wins = 0
        self.games = 0
        self.first_game_date = None
        self.last_game_date = None

    def update(self, date, is_win):
        self.games += 1
        if is_win:
            self.wins += 1
        if self.first_game_date is None or date < self.first_game_date:
            self.first_game_date = date
        if self.last_game_date is None or date > self.last_game_date:
            self.last_game_date = date

    @property
    def win_percentage(self):
        return (self.wins / self.games) * 100 if self.games > 0 else 0


def count_connections_wins():
    stats = defaultdict(ModelStats)
    posts_dir = os.path.join("content", "posts", "connections")
    for filename in os.listdir(posts_dir):
        if filename.endswith(".md"):
            file_path = os.path.join(posts_dir, filename)
            with open(file_path, "r") as file:
                content = file.read()

                # Extract model and date from filename
                filename_parts = filename.split("-")
                if len(filename_parts) >= 4:  # Ensure there are enough parts
                    model = "-".join(filename_parts[3:]).rstrip(".md")
                    date_str = "-".join(filename_parts[:3])
                    date = datetime.strptime(date_str, "%Y-%m-%d")
                else:
                    continue  # Skip files with unexpected naming format

                # Check for a win (all four colors of four-square patterns must be present)
                win_patterns = [r"🟩🟩🟩🟩", r"🟨🟨🟨🟨", r"🟦🟦🟦🟦", r"🟪🟪🟪🟪"]
                lines = content.split("\n")
                is_win = all(
                    any(pattern in line for line in lines) for pattern in win_patterns
                )

                stats[model].update(date, is_win)

                if is_win:
                    print(file_path)

    return stats


def build_stats_table(model_stats):
    table = "| Model | Wins | Games | Win % | First Game  |\n"
    table += "|-------|------|-------------|----------------|------------|\n"
    for model, stat in model_stats.items():
        table += (
            f"| {model} | {stat.wins} | {stat.games} | {stat.win_percentage:.1f}% | "
            f"{stat.first_game_date.strftime('%Y-%m-%d')} |\n"
        )
    return table.strip()


if __name__ == "__main__":
    model_stats = count_connections_wins()
    print(build_stats_table(model_stats))
