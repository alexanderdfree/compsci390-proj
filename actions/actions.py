"""
DATABASE SCHEMA:
CREATE TABLE rooms ( room_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, size_sqm INTEGER NOT NULL, bed_type TEXT NOT NULL, capacity INTEGER NOT NULL, price_per_night_eur REAL NOT NULL, bathroom_type TEXT CHECK(bathroom_type IN ('shower','bath')) NOT NULL, view TEXT CHECK(view IN ('street','garden')) NOT NULL, amenities TEXT, floor INTEGER, breakfast_fee_eur REAL NOT NULL );
CREATE TABLE bookings ( booking_id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, guest_name TEXT NOT NULL, check_in DATE NOT NULL, check_out DATE NOT NULL, num_guests INTEGER NOT NULL CHECK(num_guests > 0), breakfast BOOLEAN NOT NULL DEFAULT 0, notes TEXT, CHECK (date(check_out) > date(check_in)), FOREIGN KEY (room_id) REFERENCES rooms(room_id) );
"""

from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

# give customer options of all open hotel rooms that:
# match the amount of people
# use lowest room_ID available

# flow for initial booking
# flow to handle booking confirmation


import sqlite3

class ActionCheckSufficientFunds(Action):
    
    def name(self) -> Text:
        return "action_check_sufficient_funds"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        # hard-coded balance for tutorial purposes. in production this
        # would be retrieved from a database or an API
        balance = 1000
        transfer_amount = tracker.get_slot("amount")
        has_sufficient_funds = transfer_amount <= balance
        return [SlotSet("has_sufficient_funds", has_sufficient_funds)]

class ActionGetMatchingRooms(Action):
    def name(self) -> Text:
        return "action_get_matching_rooms"
    ###! TODO - this method returns all matching rooms given the slot preferences
    # add logic to build the SQL query
    #based on the user preference slots that have been filled
    #for each filled slot, add a corresponding condition to the SQL query
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        number_of_customers = tracker.get_slot("booking_number")
        conn = sqlite3.connect("db/IvyGate.db")
        mycur = conn.cursor()
        sql = "select name from rooms where capacity >= 2" #2 is hard coded and needs to be replaced
        mycur.execute(sql)
        matching_rooms = mycur.fetchone()
        #print(possible_rooms)
        return [SlotSet("matching_rooms", matching_rooms)]
