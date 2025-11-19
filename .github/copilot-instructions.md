# Ivy Gate B&B – Copilot instructions

## Project Instructions - DO NOT EDIT
#Assignment task:

"Agent specifications
- English language only
- Agent initiates the conversation (hint: search for pattern_session_start)
- Contextual rephrasing is ON
- Focus on building a robust agent
  - Example: booking for -2 people; making a booking in the past; these issues
  should be handled gracefully by your agent
- Scenarios: your agent MUST handle scenarios 1 and 4; the others are optional
- Scenario 1: Caller wants to make a new booking
  - Agent takes down information, checks availability, communicates total cost; asks
  user for final confirmation whether they want to book; if so, add booking to
  “bookings” tables
- Scenario 2: Caller has a question regarding an existing booking
  - Agent identifies existing booking and answers questions based on the existing
  information in the database
- Scenario 3: Caller without a booking asks about various details of the B&B (like
breakfast, smoking, bringing pets, room details)
- Scenario 4: Caller asks for information about things to do in Dalkey (this should also be
handled within scenarios 1-3)"


First, prioritize scenario 1 until its fully implemented.



## Assignment intent & scenarios
- Build an English-only Rasa-pro assistant for the Ivy Gate B&B in Dalkey that uses flows plus a SQLite DB (`db/IvyGate.db`).
- Prioritize scenario 1 (new booking) until it is robust; then support scenario 4 (things to do in Dalkey). Scenarios 2–3 are optional but must not break existing flows.
- The agent must initiate the conversation on session start (see `data/patterns.yml` → `pattern_session_start`).
- Contextual rephrasing is ON; keep responses factual and concise so rephrasing stays faithful.
- Aim for a robust agent: handle odd inputs (negative guest counts, bookings in the past, ambiguous dates) gracefully via clarification, not crashes.

## Architecture overview
- Rasa config: `config.yml` uses `CompactLLMCommandGenerator` and `FlowPolicy`; task flows live in `data/flows.yml`, patterns in `data/patterns.yml`.
- Domain & NLG: `domain.yml` defines slots (`booking_number`, `booking_date`, `matching_rooms`, `assigned_room`, `room_info`, etc.), actions, and responses like `utter_greet` and `utter_booking_complete`.
- Custom actions: implement Rasa SDK actions in `actions/actions.py`; keep class names and `name()` strings in sync with `domain.yml` (for example `action_get_matching_rooms`, `action_find_availability`).
- Persistence: `endpoints.yml` configures an SQL tracker store pointing at `sqlite:///./db/IvyGate.db`; the same DB holds the `rooms` and `bookings` tables used for availability and reservations.
- LLMs: `config.yml` and `endpoints.yml` wire `rasa/command-generator-llama-3.1-8b-instruct` for command generation and OpenAI `gpt-4o` for NLG rephrasing; do not hard-code API keys or secrets into this repo.

## Booking data model
- Tables (see the docstring in `actions/actions.py`):
  - `rooms(room_id, name, size_sqm, bed_type, capacity, price_per_night_eur, bathroom_type, view, amenities, floor, breakfast_fee_eur)`.
  - `bookings(booking_id, room_id, guest_name, check_in, check_out, num_guests, breakfast, notes)` with constraints `num_guests > 0` and `check_out > check_in`.
- Use parameterized SQL with `sqlite3` against `db/IvyGate.db`; never build queries by string concatenation.
- For scenario 1, compute availability by filtering `rooms` by capacity and excluding rooms that already have overlapping `bookings` in the requested date range.
- When inserting bookings, always validate: positive guest count, future or current dates (no bookings wholly in the past), and that selected room capacity ≥ requested guests.

## Flows, slots, and responses
- Booking flow: `data/flows.yml` → `make_booking` currently collects `booking_number` (guest count) and `booking_date`, calls `action_get_matching_rooms`, then collects `preferred_room` before `utter_booking_complete`; extend this flow rather than adding ad-hoc logic.
- Slots in `domain.yml` tagged `from_llm` (for example `booking_number`, `booking_date`) are extracted by the LLM; treat them as the single source of truth when querying or writing to the DB.
- Slots tagged `controlled` (for example `matching_rooms`, `assigned_room`, `room_info`) should be set only from custom actions and used to populate response templates like `utter_room_assignment`.
- Small-talk and knowledge questions (including "things to do in Dalkey") are handled via `data/patterns.yml` flows (`pattern_chitchat`, `pattern_search`) and `utter_free_chitchat_response` with `rephrase` metadata.

## Implementation conventions
- Use Python 3 and `rasa_sdk` idioms in `actions/actions.py`: implement `run(self, dispatcher, tracker, domain)` to read slots, talk to SQLite, and return `SlotSet` events.
- Keep `config.yml`, `domain.yml`, `data/flows.yml`, `data/patterns.yml`, and `actions/actions.py` consistent (every new action must be declared in `domain.yml` and referenced from a flow or pattern).
- Treat `tests/e2e_test_cases.yml` as the place to add Rasa-style end-to-end tests for booking scenarios; keep `tests/stub-tests.yml` for lower-level test scaffolding if you introduce it.
- If you significantly change how bookings or flows work, briefly document the new behavior and any non-obvious commands or URLs in `README.md`.
- When choosing tasks, fully implement and harden scenario 1 first (including DB writes and edge cases) before adding or refactoring logic for scenarios 2–4.