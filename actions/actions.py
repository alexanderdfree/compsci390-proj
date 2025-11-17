from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

#give customer options of all open hotel rooms that:
#match the amount of people
#use lowest room_ID available

#flow for initial booking
#flow to handle booking confirmation

#scenario 1 -
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

class ActionGetPossibleRooms(Action):
    def name(self) -> Text:
        return "action_get_possible_rooms"

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
        possible_rooms = mycur.fetchone()
        #print(possible_rooms)
        return [SlotSet("possible_rooms", possible_rooms)]