import json
import logging
import random
import re

from dataclasses import dataclass
from datetime import (
    date,
    datetime,
)
from enum import Enum
from modal import App, Image, Secret
from typing import Dict, List, Set


connections_image = Image.debian_slim(python_version="3.12").pip_install(
    "pydantic>=2.0",
    "httpx",
    "llm",
    "llm-claude-3",
    "llm-mistral",
    "llm-groq",
)

app = App(name="bots.connections")

with connections_image.imports():
    import httpx
    import llm


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FIRST_GAME_DATE = "2023-06-12"
ALLOWED_MISTAKES = 4
CATEGORY_SIZE = 4
NUM_CATEGORIES = 4

# Set a fixed seed for the random number generator for reproducibility
random.seed(42)

START_MESSAGE = """"Connections" is a word categorization game. I will provide you with 16 words, and your goal is to find four groups of four words that share a common category. Each word will belong to only one category in the correct solution. Be careful of words that seem like they could fit in more than one category. Consider guessing other categories first to improve your chances of success by elimination of other more obvious words. You have a maximum of four incorrect guesses, so choose carefully!

After I give you the words, you will suggest one group of four words at a time and the category that connects them. I will provide feedback on whether the group of four words is correct or incorrect. The accuracy of the category name is not important; what matters is that the four words belong together. If three out of the four words you guess share a category, I will let you know. Otherwise, I will simply tell you if your guess was right or wrong.

Don't get discouraged if you make invalid guesses. Keep trying! I am very patient.

The connection between words is _not_ vague. The connection is clear.

Sometimes the categories are "outside the box". Here are some examples in the form of `Category: WORD1, WORD2, WORD3, WORD4`:

- Starts of planet names: EAR, MAR, MER, SAT
- Second ___: FIDDLE, GUESS, NATURE, WIND
- Associated with "stub": CIGARETTE, PENCIL, TICKET, TOE
- ___ Dream: AMERICAN, FEVER, LUCID, PIPE

Here is a example solution to a full puzzle for further context

Words:

SPRINKLE
SPONGE
BIRD
ROSE
PICK
CHERRY
DROP
CREAM
MUD
BUBBLE
TOP
SPOT
RUBY
BEST
SPLASH
BRICK

Solution:

- A little bit of a beverage: DROP, SPLASH, SPOT, SPRINKLE
- Shades of red: BRICK, CHERRY, ROSE, RUBY
- ___  Bath: BIRD, BUBBLE, MUD, SPONGE
- Choicest: BEST, CREAM, PICK, TOP

Here are the 16 words:
{words}

Do any thinking you need to do inside <scratchpad></scratchpad> tags.
Please make your first guess.
Output guesses in the following format inside the backticks:

```
{{"<category>": ["<word_1>", "<word_2>", "<word_3>", "<word_4>"]}}
```

For example:

```
{{"Types of fish": ["SALMON", "TROUT", "BASS", "STURGEON"]}}
```

Good luck!
"""


@dataclass
class Category:
    name: str
    words: Set[str]


class GuessResult(Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    THREE_OUT_OF_FOUR = "three out of four"
    INVALID = "invalid"


@dataclass
class Guess:
    words: Set[str]
    result: GuessResult

    def __repr__(self):
        return f"Guess(words={self.words}, result={self.result.value})"


class LLMGuesser(object):
    def __init__(self, model):
        self.model = llm.get_model(model)
        self.conversation = self.model.conversation()

    def make_guess(self, prompt) -> str:
        response = self.conversation.prompt(prompt)
        return response.text()


@dataclass
class ParsedGuess:
    valid: bool
    guess_set: Set[str]
    reason: str


class GameState:
    def __init__(self, categories: List[Category]):
        self.categories = categories
        self.words = [word for category in categories for word in category.words]
        random.shuffle(self.words)
        self.remaining_mistakes = ALLOWED_MISTAKES
        self.num_correct_guesses = 0
        self.guesses: List[Guess] = []
        self.is_over = False

    def add_guess(self, guess: Guess):
        self.guesses.append(guess)
        if guess.result == GuessResult.CORRECT:
            self.num_correct_guesses += 1
        elif guess.result != GuessResult.INVALID:
            self.remaining_mistakes -= 1

    def guessed_sets(self) -> List[Set[str]]:
        return [g.words for g in self.guesses]

    def correct_guesses(self) -> List[Guess]:
        return [g for g in self.guesses if g.result == GuessResult.CORRECT]

    def any_word_already_in_correct_category(self, words: Set[str]) -> bool:
        guessed_words_set = set()
        for g in self.correct_guesses():
            guessed_words_set.update(g.words)
        return bool(words.intersection(guessed_words_set))


class GuessEvaluator:
    def __init__(self, categories: List[Category], words: List[str]):
        self.categories = categories
        self.words = words

    def parse_guess(self, guess: str) -> ParsedGuess:
        # remove scratchpad
        guess = re.sub(r"<scratchpad>.*?</scratchpad>", "", guess, flags=re.DOTALL)
        # extract json guess from inside backticks
        guess_re = re.search(r"```(.*?)```", guess, re.DOTALL)
        if guess_re:
            guess_re = guess_re.group(1).strip()
            guess_dict = json.loads(guess_re)
        else:
            guess_dict = json.loads(guess)

        guess_tokens = list(guess_dict.values())[0]

        logger.info(f"Guess tokens: {guess_tokens}")
        guess_set: Set[str] = set()
        for word in self.words:
            if word in guess_tokens:
                guess_set.add(word)
        logger.info(f"Guess set: {guess_set}")
        if len(guess_set) != CATEGORY_SIZE:
            return ParsedGuess(False, guess_set, "Your guess must contain 4 words")

        return ParsedGuess(True, guess_set, "")

    def evaluate_guess(
        self, guess_set: Set[str], guessed_sets: List[Set[str]]
    ) -> Guess:
        if guess_set in guessed_sets:
            return Guess(words=guess_set, result=GuessResult.INVALID)

        for category in self.categories:
            if category.words == guess_set:
                return Guess(words=guess_set, result=GuessResult.CORRECT)
            if len(category.words.intersection(guess_set)) == 3:
                return Guess(words=guess_set, result=GuessResult.THREE_OUT_OF_FOUR)
        return Guess(words=guess_set, result=GuessResult.INCORRECT)


class Game:
    def __init__(self, categories: List[Category], guesser: LLMGuesser):
        self.state = GameState(categories)
        self.guesser = guesser
        self.evaluator = GuessEvaluator(categories, self.state.words)
        self.prompt = START_MESSAGE.format(words="\n".join(self.state.words))

    def play(self):
        while (
            self.state.remaining_mistakes > 0
            and self.state.num_correct_guesses != NUM_CATEGORIES
        ):
            self.do_turn()
        logger.info(self.prompt)
        return self.state.num_correct_guesses == NUM_CATEGORIES

    def do_turn(self):
        logger.info(self.prompt)
        guess_model_response: str = self.guesser.make_guess(self.prompt)
        logger.info(guess_model_response)
        parsed_guess = self.evaluator.parse_guess(guess_model_response)
        if not parsed_guess.valid:
            self.prompt = f"Your guess was invalid. {parsed_guess.reason}."
            return

        if self.state.any_word_already_in_correct_category(parsed_guess.guess_set):
            self.prompt = "Your guess was invalid. You cannot use a word in more than one category."
            return

        guess_result: Guess = self.evaluator.evaluate_guess(
            parsed_guess.guess_set, self.state.guessed_sets()
        )

        if guess_result.result != GuessResult.INVALID:
            self.state.add_guess(guess_result)
        match guess_result.result:
            case GuessResult.CORRECT:
                self.prompt = f"Correct! You've guessed {self.state.num_correct_guesses}/4 groups."
            case GuessResult.THREE_OUT_OF_FOUR:
                self.prompt = (
                    "Incorrect, but three out of four words belong to the same category"
                )
            case GuessResult.INCORRECT:
                self.prompt = "Incorrect"
            case GuessResult.INVALID:
                self.prompt = "You have already guessed this group of words"

        self.prompt += f" You have {self.state.remaining_mistakes} guess{'es' if self.state.remaining_mistakes > 1 else ''} remaining."
        if self.state.correct_guesses():
            self.prompt += "\nCorrect guesses so far: "
            self.prompt += " ".join(
                [str(g.words) for g in self.state.correct_guesses()]
            )

    def result(self):
        logger.info(f"Total guesses: {len(self.state.guesses)}")
        logger.info(f"Correct guesses: {self.state.num_correct_guesses}")
        logger.info(self.state.guesses)

        if self.state.num_correct_guesses == NUM_CATEGORIES:
            logger.info("✅ LLM won")
        else:
            logger.info("❌ LLM lost")
        return self.state


def puzzle_number(end):
    start = FIRST_GAME_DATE
    first_game_date = datetime.strptime(start, "%Y-%m-%d")
    current_game_date = datetime.strptime(end, "%Y-%m-%d")
    return (current_game_date - first_game_date).days + 1


def format_game_result(
    model: str, game_date: str, categories: List[Category], guesses: List[Guess]
):
    emoji_to_category_dict: Dict[frozenset[str], str] = {
        frozenset(categories[0].words): "🟩",
        frozenset(categories[1].words): "🟨",
        frozenset(categories[2].words): "🟦",
        frozenset(categories[3].words): "🟪",
    }
    out_str = f"🤖 Connections ({model}) \nPuzzle #{puzzle_number(game_date)}\n"
    for guess in guesses:
        guess_str = ""
        for word in list(sorted(guess.words)):
            for category, emoji in emoji_to_category_dict.items():
                if word in category:
                    guess_str += emoji
                    break
        guess_str += "\n"
        out_str += guess_str
    return out_str.strip()


def fetch_game_data(game_date):
    url = f"https://www.nytimes.com/svc/connections/v2/{game_date}.json"
    with httpx.Client() as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


@app.function(image=connections_image, secrets=[Secret.from_name("bots-doing-things")])
def play_game(model: str):
    game_date = date.today().strftime("%Y-%m-%d")
    logger.info(game_date)
    game_data = fetch_game_data(game_date)
    categories = [
        Category(
            name=c["title"],
            words=set([w["content"] for w in c["cards"]]),
        )
        for c in game_data["categories"]
    ]
    logger.info(categories)

    guesser = LLMGuesser(model)
    game = Game(categories, guesser)
    game.play()
    game.result()
    result = format_game_result(
        model,
        game_date,
        categories,
        game.state.guesses,
    )
    logger.info(result)
    return result
