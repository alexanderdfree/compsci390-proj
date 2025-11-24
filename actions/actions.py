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

# class ActionGetMatchingRooms(Action):
# this function returns a list of room IDs that match the slots representing the customer's requirements
# these room IDs are stored in the slot "matching_rooms" as a list of ints

class ActionGetAvailableRoom(Action):
    def name(self) -> Text:
        return "action_get_available_room"
    # Firstly, this function only checks for available rooms from the list of room IDs stored in the slot "matching_room_ids".
    # This function takes the checkin and checkout dates and the number of people traveling.
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
            WITH booked_rooms AS
                (SELECT DISTINCT room_id
                FROM bookings 
                WHERE (date(?) <= check_in AND date(?) > check_out) 
                OR (date(?) < check_in AND date(?) >= check_out) 
                OR (date(?) >= check_in AND date(?) <= check_out)
                ) 
            SELECT room_id, name FROM rooms WHERE room_id NOT IN booked_rooms
            AND capacity >= ?;
        """
        mycur.execute(sql, (date_checkin, date_checkout, date_checkin, date_checkout, date_checkin, date_checkout, number_of_customers))
        available_room = mycur.fetchone()
        print("room_id: {0}, room_name: {1}".format(available_room[0], available_room[1]))
        #print(possible_rooms)
        return [SlotSet("assigned_room", available_room[0]), SlotSet("room_info", available_room[1])]

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
        room_id = tracker.get_slot("room_id")
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
