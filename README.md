# Guava spell-back pacing

I built two versions of a meeting-booking agent to test whether slower spell-back pacing helps callers catch misspellings, but found that speech_speed="x-slow" didn’t measurably slow the spell-back in my tests.

To run: `guava login`, then `uv sync`, set `GUAVA_AGENT_NUMBER` to your Guava phone number, run `uv run python prototype-a/prototype_a.py` (or `prototype-b/prototype_b.py`), and call that number. Tests run offline with `uv run python -m unittest` from each prototype's folder.

## Prototype A

The agent spelled my name back letter by letter, but I had to correct it like this:

“First name, Ann: A, N as in Nancy, N as in Nancy. Last name, Demeulemeester: D as in David, E, M as in Mary, E, U, L, E, M as in Mary, double E, S as in Sam, T as in Tom, E, R.”

The agent recorded `D E M U L E M E E S T E R`, missing the E after the first M. It spelled that back and I confirmed "yes," because the spell-back was too fast for me to catch the mistake.

Side note: on another call I asked “You got that?” after spelling my name, and my `on_question` handler returned an unhelpful answer, probably because my confirmation step could only handle “yes” or “no.” I like that the SDK puts Python in charge of the flow: a more generative design might handle that more gracefully, but it would be harder to test.

## Prototype B

Before the name spell-back, the code switches the speech speed to “x-slow” with `set_persona(speech_speed="x-slow")`, then back to normal afterwards. I used "x-slow" because "slow" didn't sound different from the default.

- [Before (Prototype A)](clips/prototype-a.m4a)
- [After (Prototype B)](clips/prototype-b.m4a)

Result: I timed the spell-back in each recording: 5.57 seconds for A and 5.76 for B, which is within stopwatch error, so B wasn't measurably slower. I also tried "x-slow" for the whole call, set the same way as Guava's own slow-speech example, and it didn't sound slower either.

On the B call I did catch a misspelling and correct it, but that really can't be credited to pacing since it wasn't significantly slower. The agent then went silent for about 13 and 16 seconds, long enough to make a caller hang up; I don't know whether my code or the platform caused this. It also still saved the misheard name due to a bug in my code (noted as a known issue in the code).

## Testing and next steps

Both prototypes log what the agent recorded at each step (e.g. `Heard spelling: 'A N N / D E M U L E M E E S T E R'`), which is how I caught the missing E. Automated tests check that B sends the slow-speech setting only for the name spell-back, but not whether the speech actually slows.

First, I'd confirm the speed setting changes the speech rate, by timing the same sentence at each setting. If it does, I'd measure whether slower pacing helps: how often misheard spellings are caught and corrected, whether the right name is saved, and how much time it costs. Potential methods:

- Recorded hard-to-spell names run through `test_audio()`, to measure ASR accuracy.
- Voice-based call simulations, though a simulated caller adds its own speech recognition and turn-taking errors, and may not struggle with fast spelling the way a person does.
- Live test calls with real people, since whether a spell-back is too fast to follow is a human judgment.
