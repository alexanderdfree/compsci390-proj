# compsci390 – Ivy Gate B&B assistant

by Alex, Andrew, and Spencer

## Scenario 1: New booking

This project implements a Rasa assistant for the Ivy Gate B&B in Dalkey.

The primary supported flow is **Scenario 1 – caller wants to make a new booking**:

- The assistant greets the caller on session start.
- The `make_booking` flow in `data/flows.yml` collects:
	- number of guests (`booking_number`)
	- check-in and check-out dates (`booking_date`)
	- guest name (`guest_name`)
	- preferred room from the available options (`preferred_room`)
	- whether breakfast should be included (`include_breakfast`)
- Custom actions in `actions/actions.py` then:
	- validate guest count and dates (no negative guests, no stays entirely in the past)
	- check room availability against `db/IvyGate.db` (`ActionGetMatchingRooms`)
	- summarise the proposed booking and total cost (`ActionSummarizeBooking`)
	- on explicit confirmation, write a row to the `bookings` table (`ActionCreateBooking`).

The flow always asks for **final confirmation** before inserting into the database.

### Quick start (local)

From the project root:

```bash
rasa run actions
```

In a separate terminal:

```bash
rasa shell
```

Make sure you configure your OpenAI API key (for NLG rephrasing) in an environment
variable, for example via the `.env` file created in this repo.

### Helper tests

There is a small Python test module for booking helpers:

- `tests/test_booking_actions_helpers.py` exercises date parsing, guest count
	validation, and the availability query against the seeded `IvyGate.db` data.

You can run these tests manually with:

```bash
python -m tests.test_booking_actions_helpers
```

