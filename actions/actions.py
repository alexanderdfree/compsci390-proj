"""
DATABASE SCHEMA:
CREATE TABLE rooms (
    room_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    size_sqm INTEGER NOT NULL,
    bed_type TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    price_per_night_eur REAL NOT NULL,
    bathroom_type TEXT CHECK(bathroom_type IN ('shower','bath')) NOT NULL,
    view TEXT CHECK(view IN ('street','garden')) NOT NULL,
    amenities TEXT,
    floor INTEGER,
    breakfast_fee_eur REAL NOT NULL
);

CREATE TABLE bookings (
    booking_id INTEGER PRIMARY KEY,
    room_id INTEGER NOT NULL,
    guest_name TEXT NOT NULL,
    check_in DATE NOT NULL,
    check_out DATE NOT NULL,
    num_guests INTEGER NOT NULL CHECK(num_guests > 0),
    breakfast BOOLEAN NOT NULL DEFAULT 0,
    notes TEXT,
    CHECK (date(check_out) > date(check_in)),
    FOREIGN KEY (room_id) REFERENCES rooms(room_id)
);
"""

from typing import Any, Dict, List, Text
import os

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

import sqlite3
import dateparser


DB_PATH = "./db/IvyGate.db"


def get_db_connection():
    """Create a database connection with error handling."""
    try:
        conn = sqlite3.connect(DB_PATH)
        return conn
    except sqlite3.Error as e:
        print(f"Database connection error: {e}")
        return None


def parse_date_to_string(date_str: str) -> str:
    """Parse a date string and return it in YYYY-MM-DD format for SQLite."""
    if not date_str:
        return None
    parsed = dateparser.parse(date_str, date_formats=['%Y-%m-%d'])
    if parsed:
        return parsed.strftime('%Y-%m-%d')
    return None


class ActionSummarizeBooking(Action):
    def name(self) -> Text:
        return "action_summarize_booking"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        # Get slot values
        room_id = tracker.get_slot("assigned_room")
        check_in_str = tracker.get_slot("check_in_date")
        check_out_str = tracker.get_slot("check_out_date")
        num_guests = tracker.get_slot("num_guests")
        include_breakfast = tracker.get_slot("include_breakfast")
        guest_name = tracker.get_slot("guest_name")

        # Parse dates
        check_in = dateparser.parse(check_in_str, date_formats=["%Y-%m-%d"]) if check_in_str else None
        check_out = dateparser.parse(check_out_str, date_formats=["%Y-%m-%d"]) if check_out_str else None

        if not all([room_id, check_in, check_out, num_guests, guest_name]):
            dispatcher.utter_message(
                text="Sorry, I'm missing some booking details. Let's start over."
            )
            return [SlotSet("booking_summary", None), SlotSet("total_cost", None)]

        # Calculate number of nights
        num_nights = (check_out - check_in).days

        # Get room details from database
        conn = get_db_connection()
        if conn is None:
            dispatcher.utter_message(text="Sorry, I'm having trouble accessing the booking system.")
            return [SlotSet("booking_summary", None), SlotSet("total_cost", None)]

        try:
            mycur = conn.cursor()
            sql = """
                SELECT name, price_per_night_eur, breakfast_fee_eur, bed_type, 
                       view, bathroom_type, amenities, size_sqm, floor
                FROM rooms WHERE room_id = ?
            """
            # Convert room_id to int in case it's stored as string
            mycur.execute(sql, (int(room_id),))
            room = mycur.fetchone()
        except sqlite3.Error as e:
            print(f"Database error in ActionSummarizeBooking: {e}")
            dispatcher.utter_message(text="Sorry, I couldn't retrieve the room details.")
            return [SlotSet("booking_summary", None), SlotSet("total_cost", None)]
        finally:
            conn.close()

        if room is None:
            dispatcher.utter_message(text="Sorry, I couldn't find the room details.")
            return [SlotSet("booking_summary", None), SlotSet("total_cost", None)]

        (
            room_name,
            price_per_night,
            breakfast_fee,
            bed_type,
            view,
            bathroom_type,
            amenities,
            size_sqm,
            floor,
        ) = room

        # Calculate total cost
        room_cost = price_per_night * num_nights
        breakfast_cost = 0.0
        if include_breakfast:
            # Breakfast fee is per person per night
            breakfast_cost = breakfast_fee * num_nights * int(num_guests)
        total_cost = room_cost + breakfast_cost

        # Create booking summary dictionary
        booking_summary = {
            "guest_name": guest_name,
            "room_name": room_name,
            "room_id": int(room_id),
            "check_in": check_in.strftime("%Y-%m-%d"),
            "check_out": check_out.strftime("%Y-%m-%d"),
            "num_nights": num_nights,
            "num_guests": int(num_guests),
            "include_breakfast": include_breakfast,
            "price_per_night": price_per_night,
            "room_cost": room_cost,
            "breakfast_cost": breakfast_cost,
            "total_cost": total_cost,
            "bed_type": bed_type,
            "view": view,
            "bathroom_type": bathroom_type,
            "amenities": amenities,
            "size_sqm": size_sqm,
            "floor": floor,
        }

        # Format and dispatch summary message
        breakfast_text = "Yes" if include_breakfast else "No"
        summary_msg = (
            f"Here's your booking summary:\n"
            f"• Guest: {guest_name}\n"
            f"• Room: {room_name} ({bed_type} bed, {view} view)\n"
            f"• Dates: {check_in.strftime('%B %d, %Y')} to {check_out.strftime('%B %d, %Y')} ({num_nights} night{'s' if num_nights > 1 else ''})\n"
            f"• Guests: {int(num_guests)}\n"
            f"• Breakfast included: {breakfast_text}\n"
            f"• Room cost: €{room_cost:.2f}\n"
            f"• Breakfast cost: €{breakfast_cost:.2f}\n"
            f"• Total: €{total_cost:.2f}"
        )
        dispatcher.utter_message(text=summary_msg)

        return [
            SlotSet("booking_summary", booking_summary),
            SlotSet("total_cost", total_cost),
        ]


class ActionLookupBooking(Action):
    def name(self) -> Text:
        return "action_lookup_booking"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        booking_id = tracker.get_slot("booking_id_lookup")

        if not booking_id:
            dispatcher.utter_message(text="I need a booking ID to look up your reservation.")
            return [SlotSet("booking_info", None)]

        conn = get_db_connection()
        if conn is None:
            dispatcher.utter_message(text="Sorry, I'm having trouble accessing the booking system.")
            return [SlotSet("booking_info", None)]

        try:
            mycur = conn.cursor()
            sql = """
                SELECT b.booking_id, b.guest_name, b.check_in, b.check_out, 
                       b.num_guests, b.breakfast, b.notes,
                       r.room_id, r.name, r.size_sqm, r.bed_type, r.capacity, 
                       r.price_per_night_eur, r.bathroom_type, r.view, 
                       r.amenities, r.floor, r.breakfast_fee_eur
                FROM bookings b
                JOIN rooms r ON b.room_id = r.room_id
                WHERE b.booking_id = ?
            """
            mycur.execute(sql, (booking_id,))
            result = mycur.fetchone()
        except sqlite3.Error as e:
            print(f"Database error in ActionLookupBooking: {e}")
            dispatcher.utter_message(text="Sorry, I couldn't search for that booking.")
            return [SlotSet("booking_info", None)]
        finally:
            conn.close()

        if result is None:
            dispatcher.utter_message(
                text=f"I couldn't find a booking with ID {booking_id}."
            )
            return [SlotSet("booking_info", None)]

        # Calculate total cost for the booking
        check_in = dateparser.parse(result[2], date_formats=["%Y-%m-%d"])
        check_out = dateparser.parse(result[3], date_formats=["%Y-%m-%d"])
        num_nights = (check_out - check_in).days
        room_cost = result[12] * num_nights
        breakfast_cost = result[17] * num_nights * result[4] if result[5] else 0
        total_cost = room_cost + breakfast_cost

        booking_info = {
            "booking_id": result[0],
            "guest_name": result[1],
            "check_in": result[2],
            "check_out": result[3],
            "num_guests": result[4],
            "breakfast": bool(result[5]),
            "notes": result[6],
            "room_id": result[7],
            "room_name": result[8],
            "room_size_sqm": result[9],
            "bed_type": result[10],
            "capacity": result[11],
            "price_per_night_eur": result[12],
            "bathroom_type": result[13],
            "view": result[14],
            "amenities": result[15],
            "floor": result[16],
            "breakfast_fee_eur": result[17],
            "num_nights": num_nights,
            "total_cost": total_cost,
        }

        return [SlotSet("booking_info", booking_info)]


class ActionGetAvailableRoom(Action):
    def name(self) -> Text:
        return "action_get_available_room"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        # Get slot values with validation
        number_of_customers = tracker.get_slot("num_guests")
        check_in_str = tracker.get_slot("check_in_date")
        check_out_str = tracker.get_slot("check_out_date")

        # Validate required slots exist
        if number_of_customers is None or check_in_str is None or check_out_str is None:
            print(f"Missing slot values: num_guests={number_of_customers}, check_in={check_in_str}, check_out={check_out_str}")
            dispatcher.utter_message(text="I'm missing some booking information. Could you please provide the dates and number of guests again?")
            return [
                SlotSet("assigned_room", None),
                SlotSet("room_info", None),
                SlotSet("room_available", False),
            ]

        # Convert num_guests to integer for SQL comparison
        try:
            num_guests_int = int(float(number_of_customers))
        except (ValueError, TypeError):
            print(f"Invalid num_guests value: {number_of_customers}")
            dispatcher.utter_message(text="I couldn't understand the number of guests. Please provide a number between 1 and 10.")
            return [
                SlotSet("assigned_room", None),
                SlotSet("room_info", None),
                SlotSet("room_available", False),
            ]

        # Parse dates and convert to YYYY-MM-DD strings for SQLite
        date_checkin = parse_date_to_string(check_in_str)
        date_checkout = parse_date_to_string(check_out_str)

        if date_checkin is None or date_checkout is None:
            print(f"Date parsing failed: check_in={check_in_str} -> {date_checkin}, check_out={check_out_str} -> {date_checkout}")
            dispatcher.utter_message(text="I couldn't understand the dates. Please provide them in a format like 'December 15, 2025' or '2025-12-15'.")
            return [
                SlotSet("assigned_room", None),
                SlotSet("room_info", None),
                SlotSet("room_available", False),
            ]

        print(f"Searching for room: checkin={date_checkin}, checkout={date_checkout}, guests={num_guests_int}")

        # Connect to database
        conn = get_db_connection()
        if conn is None:
            dispatcher.utter_message(text="Sorry, I'm having trouble accessing the booking system. Please try again.")
            return [
                SlotSet("assigned_room", None),
                SlotSet("room_info", None),
                SlotSet("room_available", False),
            ]

        try:
            mycur = conn.cursor()
            
            # SQL query to find available room
            # Uses string dates in YYYY-MM-DD format for proper SQLite date comparison
            sql = """
                SELECT r.room_id, r.name, r.size_sqm, r.bed_type, r.capacity,
                    r.price_per_night_eur, r.bathroom_type, r.view, r.amenities,
                    r.floor, r.breakfast_fee_eur
                FROM rooms r
                WHERE r.capacity >= ?
                AND r.room_id NOT IN (
                    SELECT b.room_id FROM bookings b
                    WHERE date(?) < date(b.check_out) AND date(b.check_in) < date(?)
                )
                LIMIT 1
            """
            
            # Pass date strings (not datetime objects) for proper SQLite date() function handling
            mycur.execute(sql, (num_guests_int, date_checkin, date_checkout))
            available_room = mycur.fetchone()
            
        except sqlite3.Error as e:
            print(f"Database error in ActionGetAvailableRoom: {e}")
            dispatcher.utter_message(text="Sorry, I encountered an error checking room availability.")
            return [
                SlotSet("assigned_room", None),
                SlotSet("room_info", None),
                SlotSet("room_available", False),
            ]
        finally:
            conn.close()

        if available_room is None:
            print("No available rooms found")
            return [
                SlotSet("assigned_room", None),
                SlotSet("room_info", None),
                SlotSet("room_available", False),
            ]

        # Extract room details
        room_id = available_room[0]
        room_name = available_room[1]
        size_sqm = available_room[2]
        bed_type = available_room[3]
        capacity = available_room[4]
        price_per_night = available_room[5]
        bathroom_type = available_room[6]
        view = available_room[7]
        amenities = available_room[8]
        floor = available_room[9]

        # Build detailed room info string
        room_info = (
            f"{room_name} - {size_sqm}sqm, {bed_type} bed, {view} view, "
            f"{bathroom_type}, Floor {floor}, €{price_per_night:.2f}/night"
        )
        if amenities:
            room_info += f". Amenities: {amenities}"

        print(f"Found available room: room_id={room_id}, name={room_name}")

        # IMPORTANT: Convert room_id to string since assigned_room slot is type: text
        return [
            SlotSet("assigned_room", str(room_id)),
            SlotSet("room_info", room_info),
            SlotSet("room_available", True),
        ]


class ActionMakeBooking(Action):
    def name(self) -> Text:
        return "action_make_booking"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        # Get all required slot values
        customer_name = tracker.get_slot("guest_name")
        number_of_customers = tracker.get_slot("num_guests")
        check_in_str = tracker.get_slot("check_in_date")
        check_out_str = tracker.get_slot("check_out_date")
        customer_wants_breakfast = tracker.get_slot("include_breakfast")
        room_id = tracker.get_slot("assigned_room")

        # Validate all required values exist
        if not all([customer_name, number_of_customers, check_in_str, check_out_str, room_id]):
            dispatcher.utter_message(text="Sorry, I'm missing some booking details. Let's start over.")
            return [SlotSet("booking_id", None)]

        # Parse dates to YYYY-MM-DD format strings
        date_checkin = parse_date_to_string(check_in_str)
        date_checkout = parse_date_to_string(check_out_str)

        if date_checkin is None or date_checkout is None:
            dispatcher.utter_message(text="Sorry, there was an issue with the dates. Please try again.")
            return [SlotSet("booking_id", None)]

        # Convert types appropriately
        try:
            room_id_int = int(room_id)
            num_guests_int = int(float(number_of_customers))
        except (ValueError, TypeError) as e:
            print(f"Type conversion error: {e}")
            dispatcher.utter_message(text="Sorry, there was an issue processing your booking.")
            return [SlotSet("booking_id", None)]

        # Convert breakfast to integer for SQLite (0 or 1)
        breakfast_int = 1 if customer_wants_breakfast else 0

        print(f"Creating booking: checkin={date_checkin}, checkout={date_checkout}, name={customer_name}, "
              f"guests={num_guests_int}, breakfast={breakfast_int}, room_id={room_id_int}")

        # Connect to database
        conn = get_db_connection()
        if conn is None:
            dispatcher.utter_message(text="Sorry, I couldn't save your booking. Please try again.")
            return [SlotSet("booking_id", None)]

        try:
            mycur = conn.cursor()
            sql = """
                INSERT INTO bookings (room_id, guest_name, check_in, check_out, num_guests, breakfast)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            mycur.execute(sql, (room_id_int, customer_name, date_checkin, date_checkout, num_guests_int, breakfast_int))
            conn.commit()
            booking_id = mycur.lastrowid
            print(f"Booking created successfully: booking_id={booking_id}")
        except sqlite3.Error as e:
            print(f"Database error in ActionMakeBooking: {e}")
            dispatcher.utter_message(text="Sorry, I couldn't save your booking due to a system error.")
            return [SlotSet("booking_id", None)]
        finally:
            conn.close()

        # Return booking_id as string since slot is type: text
        return [SlotSet("booking_id", str(booking_id))]