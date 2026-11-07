# PadelCred promise tests

Each test checks one promise PadelCred makes to players: a number on a help page, a rule a screen describes, or something a feature claims to do. If a test fails, the app isn't doing what it tells players it does.

Run these before every release. A release only goes out when every promise is kept.

## How to run (Claude Code can do this for you)

1. Install the tools once: `pip install playwright` then `playwright install chromium`
2. In the folder with the app files, start a local copy: `python3 -m http.server 8000`
3. In a second Terminal window: `python3 tests/promises.py http://localhost:8000`

It prints PASS or FAIL for each promise, then "N of N promises kept".

## Adding a promise

When the app starts making a new claim (a new help line, a new rule, a new feature), add a test for it in `promises.py` with the claim in plain English and where the app makes it.

## Test-only access

The tests open the app with `?selftest=1`, which gives them read access to the app's maths. It does nothing for players, who never use that address.
