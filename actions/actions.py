"""
DATABASE SCHEMA:
CREATE TABLE rooms ( room_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, size_sqm INTEGER NOT NULL, bed_type TEXT NOT NULL, capacity INTEGER NOT NULL, price_per_night_eur REAL NOT NULL, bathroom_type TEXT CHECK(bathroom_type IN ('shower','bath')) NOT NULL, view TEXT CHECK(view IN ('street','garden')) NOT NULL, amenities TEXT, floor INTEGER, breakfast_fee_eur REAL NOT NULL );
CREATE TABLE bookings ( booking_id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, guest_name TEXT NOT NULL, check_in DATE NOT NULL, check_out DATE NOT NULL, num_guests INTEGER NOT NULL CHECK(num_guests > 0), breakfast BOOLEAN NOT NULL DEFAULT 0, notes TEXT, CHECK (date(check_out) > date(check_in)), FOREIGN KEY (room_id) REFERENCES rooms(room_id) );
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher


logger = logging.getLogger(__name__)

DB_PATH = "db/IvyGate.db"


def _parse_single_date(text: str) -> date:
    """Parse a single date from natural text.

    Supports a handful of common formats, falling back to assuming the
    current or next year if the user omits the year.
    """

    text_clean = " ".join(str(text).strip().replace(",", " ").split())

    # Try ISO and numeric formats first
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text_clean, fmt).date()
        except ValueError:
            continue

    # Try formats with month names. If year is missing, assume this year or next.
    today = date.today()
    for fmt in (
        "%b %d %Y",
        "%B %d %Y",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d",
        "%B %d",
        "%d %b",
        "%d %B",
    ):
        try:
            dt = datetime.strptime(text_clean, fmt)
            if dt.year == 1900:  # year omitted
                dt = dt.replace(year=today.year)
                if dt.date() < today:
                    dt = dt.replace(year=today.year + 1)
            return dt.date()
        except ValueError:
            continue

    raise ValueError(f"Could not parse date from '{text}'.")


def parse_booking_date_range(raw: str) -> Tuple[date, date]:
    """Parse a booking date range from natural text.

    The `booking_date` slot may contain either a single date or a range like
    "2025-11-20 to 2025-11-22". If only a single date is given, we assume a
    one-night stay.
    """

    if not raw:
        raise ValueError("Empty date range.")

    text = " ".join(str(raw).strip().split())

    # Look for common range separators
    for sep in [" to ", " until ", " through ", " till ", " - "]:
        if sep in text:
            left, right = text.split(sep, 1)
            check_in = _parse_single_date(left)
            check_out = _parse_single_date(right)
            break
    else:
        # Single date -> default to one-night stay
        check_in = _parse_single_date(text)
        check_out = check_in + timedelta(days=1)

    if check_out <= check_in:
        raise ValueError("Check-out date must be after check-in date.")

    return check_in, check_out


def normalize_guest_count(raw: Any) -> int:
    """Normalise the guest count slot value into a positive integer.

    Raises ``ValueError`` if the value is missing, non-numeric, fractional,
    or not strictly positive.
    """

    if raw is None:
        raise ValueError("Guest count is missing.")

    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        try:
            value = float(str(raw))
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError("Guest count must be a number.") from exc

    if not float(value).is_integer():
        raise ValueError("Guest count must be a whole number.")

    num = int(value)
    if num <= 0:
        raise ValueError("Guest count must be positive.")

    return num


def normalize_bool(raw: Any) -> Optional[bool]:
    """Convert a free-form value into ``True`` / ``False`` / ``None``.

    This is helpful because LLM-filled slots may come in as strings rather
    than real booleans.
    """

    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw

    text = str(raw).strip().lower()
    if text in {"yes", "y", "true", "1", "sure", "ok", "okay"}:
        return True
    if text in {"no", "n", "false", "0", "nope"}:
        return False

    return None


def find_available_rooms(
    num_guests: int, check_in: date, check_out: date
) -> List[Dict[str, Any]]:
    """Return a list of rooms that can host ``num_guests`` and are free.

    A room is considered available if it has sufficient capacity and there is
    no existing booking whose date range overlaps with the requested stay.
    """

    query = """
        SELECT room_id,
               name,
               capacity,
               price_per_night_eur,
               breakfast_fee_eur
        FROM rooms
        WHERE capacity >= ?
          AND NOT EXISTS (
                SELECT 1
                FROM bookings b
                WHERE b.room_id = rooms.room_id
                  AND date(b.check_in) < date(?)
                  AND date(b.check_out) > date(?)
          )
        ORDER BY price_per_night_eur ASC, room_id ASC
    """

    params = (num_guests, check_out.isoformat(), check_in.isoformat())

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()

    return [
        {
            "room_id": row["room_id"],
            "name": row["name"],
            "capacity": row["capacity"],
            "price_per_night_eur": row["price_per_night_eur"],
            "breakfast_fee_eur": row["breakfast_fee_eur"],
        }
        for row in rows
    ]


def format_room_options_message(
    rooms: List[Dict[str, Any]],
    num_guests: int,
    check_in: date,
    check_out: date,
) -> str:
    """Create a human-readable description of available rooms."""

    nights = (check_out - check_in).days

    if not rooms:
        return (
            f"Unfortunately I don't have any rooms that can accommodate {num_guests} guest(s) "
            f"from {check_in.isoformat()} to {check_out.isoformat()}."
        )

    lines: List[str] = [
        f"For {num_guests} guest(s) from {check_in.isoformat()} to {check_out.isoformat()} "
        f"({nights} night{'s' if nights != 1 else ''}), I can offer:",
    ]

    for r in rooms:
        base_total = r["price_per_night_eur"] * nights
        breakfast_total = r["breakfast_fee_eur"] * num_guests * nights
        lines.append(
            f"- {r['name']} (up to {r['capacity']} guests) at €{r['price_per_night_eur']:.2f} per night; "
            f"room-only approx. €{base_total:.2f} total, or about €{base_total + breakfast_total:.2f} "
            f"including breakfast for everyone."
        )

    lines.append("Which room would you like to book?")

    return "\n".join(lines)


class ActionGetMatchingRooms(Action):
    """Action used in the main booking flow to list available rooms.

    It reads the `booking_number` and `booking_date` slots, validates them,
    computes availability against the SQLite database, and stores both a
    structured representation in the `matching_rooms` slot and a
    human-readable summary message.
    """

    def name(self) -> str:  # pragma: no cover - Rasa interface
        return "action_get_matching_rooms"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[str, Any],  # pragma: no cover - typing only
    ) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []

        raw_guests = tracker.get_slot("booking_number")
        raw_dates = tracker.get_slot("booking_date")

        try:
            num_guests = normalize_guest_count(raw_guests)
        except ValueError as exc:
            dispatcher.utter_message(
                text=(
                    "I need a valid positive number of guests to check availability. "
                    f"{exc} Please tell me how many people will be staying."
                )
            )
            return events

        if not raw_dates:
            dispatcher.utter_message(
                text=(
                    "To look for rooms I also need your check-in and check-out dates. "
                    "For example: '2025-11-20 to 2025-11-22'."
                )
            )
            return events

        try:
            check_in, check_out = parse_booking_date_range(raw_dates)
        except ValueError as exc:
            logger.info("Could not parse booking_date '%s': %s", raw_dates, exc)
            dispatcher.utter_message(
                text=(
                    "I couldn't quite understand those dates. "
                    "Please specify your check-in and check-out, for example '2025-11-20 to 2025-11-22'."
                )
            )
            return events

        today = date.today()
        if check_out <= today:
            dispatcher.utter_message(
                text=(
                    "I can only make bookings for today or future dates. "
                    "Could you share a new check-in and check-out date?"
                )
            )
            return events

        rooms = find_available_rooms(num_guests, check_in, check_out)

        # Store structured data for downstream actions.
        events.append(SlotSet("check_in_date", check_in.isoformat()))
        events.append(SlotSet("check_out_date", check_out.isoformat()))
        # Normalise the booking_date slot into a clear range string.
        events.append(
            SlotSet("booking_date", f"{check_in.isoformat()} to {check_out.isoformat()}")
        )
        events.append(SlotSet("matching_rooms", json.dumps(rooms)))

        message = format_room_options_message(rooms, num_guests, check_in, check_out)
        dispatcher.utter_message(text=message)

        return events


class ActionFindAvailability(Action):
    """Lightweight action to answer "what's available" style questions.

    It mirrors the core availability computation of ``ActionGetMatchingRooms``
    but is safe to use outside of the main booking flow (for example when the
    caller just wants to know what rooms are free).
    """

    def name(self) -> str:  # pragma: no cover - Rasa interface
        return "action_find_availability"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[str, Any],  # pragma: no cover - typing only
    ) -> List[Dict[str, Any]]:
        raw_guests = tracker.get_slot("booking_number")
        raw_dates = tracker.get_slot("booking_date")

        try:
            num_guests = normalize_guest_count(raw_guests)
        except ValueError as exc:
            dispatcher.utter_message(
                text=(
                    "To check availability I need to know how many guests you're booking for. "
                    f"{exc}"
                )
            )
            return []

        if not raw_dates:
            dispatcher.utter_message(
                text=(
                    "To check availability, please tell me your check-in and check-out dates, "
                    "for example '2025-11-20 to 2025-11-22'."
                )
            )
            return []

        try:
            check_in, check_out = parse_booking_date_range(raw_dates)
        except ValueError as exc:
            logger.info("Could not parse booking_date '%s' in availability check: %s", raw_dates, exc)
            dispatcher.utter_message(
                text=(
                    "I couldn't quite understand those dates. "
                    "Please specify your check-in and check-out, for example '2025-11-20 to 2025-11-22'."
                )
            )
            return []

        today = date.today()
        if check_out <= today:
            dispatcher.utter_message(
                text=(
                    "I can only check availability for today or future dates. "
                    "Could you share a new date range?"
                )
            )
            return []

        rooms = find_available_rooms(num_guests, check_in, check_out)
        message = format_room_options_message(rooms, num_guests, check_in, check_out)
        dispatcher.utter_message(text=message)

        # This action is informational only; we don't need to update any slots.
        return []


class ActionSummarizeBooking(Action):
    """Summarise the proposed booking, including an estimated total cost.

    This action does *not* write to the database. Instead it explains the
    booking details and total cost, then asks the caller for final
    confirmation.
    """

    def name(self) -> str:  # pragma: no cover - Rasa interface
        return "action_summarize_booking"

    def _choose_room(
        self, preferred: Optional[str], rooms: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not rooms:
            return None

        if not preferred:
            return rooms[0]

        preferred_text = str(preferred).strip().lower()

        # Try to match by room_id or by (partial) name
        for r in rooms:
            if preferred_text == str(r.get("room_id", "")).lower():
                return r
            name = str(r.get("name", "")).lower()
            if preferred_text in name:
                return r

        # Fallback to the first offered room
        return rooms[0]

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[str, Any],  # pragma: no cover - typing only
    ) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []

        raw_guests = tracker.get_slot("booking_number")
        raw_rooms = tracker.get_slot("matching_rooms")
        preferred = tracker.get_slot("preferred_room")
        include_breakfast_raw = tracker.get_slot("include_breakfast")
        check_in_str = tracker.get_slot("check_in_date")
        check_out_str = tracker.get_slot("check_out_date")
        guest_name = tracker.get_slot("guest_name")

        try:
            num_guests = normalize_guest_count(raw_guests)
        except ValueError as exc:
            dispatcher.utter_message(
                text=(
                    "I need a valid number of guests before I can summarise the booking. "
                    f"{exc}"
                )
            )
            return events

        if not (check_in_str and check_out_str):
            dispatcher.utter_message(
                text=(
                    "I seem to be missing your check-in and check-out dates. "
                    "Could you repeat them for me?"
                )
            )
            return events

        try:
            check_in = date.fromisoformat(str(check_in_str))
            check_out = date.fromisoformat(str(check_out_str))
        except ValueError:
            dispatcher.utter_message(
                text=(
                    "Something went wrong when I stored your dates. "
                    "Could you restate your check-in and check-out dates?"
                )
            )
            return events

        rooms: List[Dict[str, Any]] = []
        if raw_rooms:
            try:
                rooms = json.loads(str(raw_rooms))
            except json.JSONDecodeError:
                logger.warning("Could not decode matching_rooms slot as JSON: %r", raw_rooms)

        if not rooms:
            dispatcher.utter_message(
                text=(
                    "I couldn't see any available rooms to summarise. "
                    "Let's check availability again first."
                )
            )
            return events

        chosen = self._choose_room(preferred, rooms)
        if not chosen:
            dispatcher.utter_message(
                text=(
                    "I couldn't match your preferred room to the options I found. "
                    "Could you tell me which room you'd like by name or number?"
                )
            )
            return events

        include_breakfast = normalize_bool(include_breakfast_raw)
        if include_breakfast is None:
            # Default to room-only if we can't tell; the follow-up question
            # asks the user to confirm anyway.
            include_breakfast = False

        nights = (check_out - check_in).days
        base_total = chosen["price_per_night_eur"] * nights
        breakfast_total = (
            chosen["breakfast_fee_eur"] * num_guests * nights if include_breakfast else 0.0
        )
        total = base_total + breakfast_total

        bf_text = "with breakfast included" if include_breakfast else "without breakfast"
        guest_prefix = f"{guest_name}, " if guest_name else ""

        summary = (
            f"{guest_prefix}staying in {chosen['name']} for {num_guests} guest(s) "
            f"from {check_in.isoformat()} to {check_out.isoformat()} "
            f"({nights} night{'s' if nights != 1 else ''}) {bf_text} will cost "
            f"approximately €{total:.2f} in total."
        )

        dispatcher.utter_message(
            text=summary + " Shall I confirm and make this booking?"
        )

        events.extend(
            [
                SlotSet("assigned_room", chosen["name"]),
                SlotSet(
                    "room_info",
                    (
                        f"Capacity {chosen['capacity']}, €{chosen['price_per_night_eur']:.2f} per night, "
                        f"breakfast €{chosen['breakfast_fee_eur']:.2f} per person per night."
                    ),
                ),
            ]
        )

        return events


class ActionCreateBooking(Action):
    """Final action in the booking flow that writes into the DB.

    It only creates a new row in the ``bookings`` table after the caller has
    explicitly confirmed that they want to proceed.
    """

    def name(self) -> str:  # pragma: no cover - Rasa interface
        return "action_create_booking"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[str, Any],  # pragma: no cover - typing only
    ) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []

        confirm_raw = tracker.get_slot("confirm_booking")
        confirm = normalize_bool(confirm_raw)
        guest_name = tracker.get_slot("guest_name")
        raw_guests = tracker.get_slot("booking_number")
        raw_rooms = tracker.get_slot("matching_rooms")
        preferred = tracker.get_slot("preferred_room")
        include_breakfast = normalize_bool(tracker.get_slot("include_breakfast"))
        check_in_str = tracker.get_slot("check_in_date")
        check_out_str = tracker.get_slot("check_out_date")

        if confirm is False:
            dispatcher.utter_message(
                text=(
                    "No problem, I won't create a booking. "
                    "If you'd like to adjust the dates or room type, just let me know."
                )
            )
            return events

        if confirm is None:
            dispatcher.utter_message(
                text="Before I proceed, please confirm if you'd like me to make this booking."
            )
            return events

        try:
            num_guests = normalize_guest_count(raw_guests)
        except ValueError as exc:
            dispatcher.utter_message(
                text=(
                    "I need a valid number of guests before I can create the booking. "
                    f"{exc}"
                )
            )
            return events

        if not guest_name:
            dispatcher.utter_message(
                text="Whose name should I put the booking under?"
            )
            return events

        if not (check_in_str and check_out_str):
            dispatcher.utter_message(
                text=(
                    "I seem to be missing the dates. "
                    "Could you remind me of your check-in and check-out dates?"
                )
            )
            return events

        try:
            check_in = date.fromisoformat(str(check_in_str))
            check_out = date.fromisoformat(str(check_out_str))
        except ValueError:
            dispatcher.utter_message(
                text=(
                    "The stored dates look invalid. "
                    "Could you restate your check-in and check-out dates?"
                )
            )
            return events

        today = date.today()
        if check_out <= today:
            dispatcher.utter_message(
                text=(
                    "I can only create bookings for today or future dates. "
                    "Let's pick a new check-in and check-out date before confirming."
                )
            )
            return events

        rooms: List[Dict[str, Any]] = []
        if raw_rooms:
            try:
                rooms = json.loads(str(raw_rooms))
            except json.JSONDecodeError:
                logger.warning(
                    "Could not decode matching_rooms when creating booking: %r", raw_rooms
                )

        if not rooms:
            dispatcher.utter_message(
                text=(
                    "I couldn't retrieve the room details I need to make the booking. "
                    "Let's search availability again."
                )
            )
            return events

        # Choose room consistently with ActionSummarizeBooking
        chosen: Optional[Dict[str, Any]]
        if preferred:
            preferred_text = str(preferred).strip().lower()
            chosen = None
            for r in rooms:
                if preferred_text == str(r.get("room_id", "")).lower():
                    chosen = r
                    break
                name = str(r.get("name", "")).lower()
                if preferred_text in name:
                    chosen = r
                    break
            if chosen is None:
                chosen = rooms[0]
        else:
            chosen = rooms[0]

        if chosen["capacity"] < num_guests:
            dispatcher.utter_message(
                text=(
                    "It looks like the selected room cannot hold that many guests. "
                    "Let's search again for a room with enough capacity."
                )
            )
            return events

        nights = (check_out - check_in).days
        base_total = chosen["price_per_night_eur"] * nights
        if include_breakfast is None:
            include_breakfast = False
        breakfast_total = (
            chosen["breakfast_fee_eur"] * num_guests * nights if include_breakfast else 0.0
        )
        total = base_total + breakfast_total

        breakfast_flag = 1 if include_breakfast else 0

        try:
            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO bookings (
                        room_id,
                        guest_name,
                        check_in,
                        check_out,
                        num_guests,
                        breakfast,
                        notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chosen["room_id"],
                        guest_name,
                        check_in.isoformat(),
                        check_out.isoformat(),
                        num_guests,
                        breakfast_flag,
                        None,
                    ),
                )
                booking_id = cur.lastrowid
                conn.commit()
        except sqlite3.Error as exc:  # pragma: no cover - defensive
            logger.exception("Error inserting booking into DB: %s", exc)
            dispatcher.utter_message(
                text="Something went wrong while saving the booking. Please try again in a moment."
            )
            return events

        message = (
            f"All set, {guest_name}! I've booked {chosen['name']} for {num_guests} guest(s) "
            f"from {check_in.isoformat()} to {check_out.isoformat()} "
            f"({'with' if include_breakfast else 'without'} breakfast included) "
            f"for an estimated total of €{total:.2f}. "
            f"Your booking ID is {booking_id}."
        )
        dispatcher.utter_message(text=message)

        events.extend(
            [
                SlotSet("assigned_room", chosen["name"]),
                SlotSet("booking_id", str(booking_id)),
            ]
        )

        return events
