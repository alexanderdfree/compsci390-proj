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

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

import sqlite3
import dateparser


# summarize booking plus calculate cost total
# store booking summary as dictionary in slot "booking_summary" and cost total in slot "total_cost"
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
        check_in = dateparser.parse(check_in_str, date_formats=["%Y-%m-%d"])
        check_out = dateparser.parse(check_out_str, date_formats=["%Y-%m-%d"])

        if not all([room_id, check_in, check_out, num_guests, guest_name]):
            dispatcher.utter_message(
                text="Sorry, I'm missing some booking details. Let's start over."
            )
            return [SlotSet("booking_summary", None), SlotSet("total_cost", None)]

        # Calculate number of nights
        num_nights = (check_out - check_in).days

        # Get room details from database
        conn = sqlite3.connect("db/IvyGate.db")
        mycur = conn.cursor()
        sql = """
            SELECT name, price_per_night_eur, breakfast_fee_eur, bed_type, 
                   view, bathroom_type, amenities, size_sqm, floor
            FROM rooms WHERE room_id = ?
        """
        mycur.execute(sql, (room_id,))
        room = mycur.fetchone()
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
            "room_id": room_id,
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


###!!! ignore this one for now
# class ActionGetMatchingRooms(Action):
# this function returns a list of room IDs that match the slots representing the customer's requirements
# these room IDs are stored in the slot "matching_rooms" as a list of ints


# lookup booking ID number, return all relevant
# information about the booking's entry, from BOTH the bookings table and rooms table
# all data from all columns, and store it in slot "booking_info" as a dictionary
# class ActionLookupBooking(Action):
# using slot booking_id_lookup
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
            return [SlotSet("booking_info", None)]

        conn = sqlite3.connect("db/IvyGate.db")
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
    # Firstly, this function only checks for available rooms from the list of room IDs stored in the slot "matching_room_ids".
    # This function takes the checkin and checkoutdates and the number of people traveling.
    # It returns the name of one room from slot room_ids that is available on those dates.
    # Note: variables are inserted into the SQL query as "?" placeholders.
    # Their values are then provided as part of the execute statement.
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        number_of_customers = tracker.get_slot("num_guests")
        date_checkin = dateparser.parse(tracker.get_slot("check_in_date"), date_formats=['%Y-%m-%d'])
        date_checkout = dateparser.parse(tracker.get_slot("check_out_date"), date_formats=['%Y-%m-%d'])
        print("checkin: {0}".format(date_checkin))
        print("checkout: {0}".format(date_checkout))
        print("number_of_customers: {0}".format(number_of_customers))

        conn = sqlite3.connect("db/IvyGate.db")
        mycur = conn.cursor()
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
        mycur.execute(sql, (number_of_customers, date_checkin, date_checkout))
        available_room = mycur.fetchone()
        if available_room is None:
            return [
                SlotSet("assigned_room", None),
                SlotSet("room_info", None),
                SlotSet("room_available", False),
            ]
        print("room_id: {0}, room_name: {1}".format(available_room[0], available_room[1]))
        # print(possible_rooms)
        return [SlotSet("assigned_room", available_room[0]), SlotSet("room_info", available_room[1]), SlotSet("room_available", True)]

class ActionMakeBooking(Action):
    def name(self) -> Text:
        return "action_make_booking"
    # This function makes a booking. To be used when there's a room available and the 
    # customer wants to do the booking.
    # Uses assigned_booking
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        customer_name = tracker.get_slot("guest_name")
        number_of_customers = tracker.get_slot("num_guests")
        date_checkin = dateparser.parse(tracker.get_slot("check_in_date"), date_formats=['%Y-%m-%d'])
        date_checkout = dateparser.parse(tracker.get_slot("check_out_date"), date_formats=['%Y-%m-%d'])
        customer_wants_breakfast = tracker.get_slot("include_breakfast")
        room_id = tracker.get_slot("assigned_room")
        print("checkin: {0}, checkout: {1}, name: {2}, number_customers: {3}, breakfast: {4}, room_id: {5}".format(date_checkin, date_checkout, customer_name, number_of_customers, customer_wants_breakfast, room_id))

        conn = sqlite3.connect("db/IvyGate.db")
        mycur = conn.cursor()
        sql = """
            INSERT INTO bookings (room_id, guest_name, check_in, check_out, num_guests, breakfast)
            VALUES (?,?,?,?,?,?)
        """
        mycur.execute(sql, (room_id, customer_name, date_checkin, date_checkout, number_of_customers, customer_wants_breakfast))
        conn.commit() # Writing the changes into the database.
        booking_id = mycur.lastrowid # This is the booking_id returned from the database.
        print("booking_id = {0}".format(booking_id))
        return [SlotSet("booking_id", booking_id)]
