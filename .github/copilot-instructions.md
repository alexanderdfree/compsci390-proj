Assignment task:

Agent specifications
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
handled within scenarios 1-3)


First, prioritize scenario 1 until its fully implemented.



DATABASE SCHEMA:

CREATE TABLE rooms ( room_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, size_sqm INTEGER NOT NULL, bed_type TEXT NOT NULL, capacity INTEGER NOT NULL, price_per_night_eur REAL NOT NULL, bathroom_type TEXT CHECK(bathroom_type IN ('shower','bath')) NOT NULL, view TEXT CHECK(view IN ('street','garden')) NOT NULL, amenities TEXT, floor INTEGER, breakfast_fee_eur REAL NOT NULL );

CREATE TABLE bookings ( booking_id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, guest_name TEXT NOT NULL, check_in DATE NOT NULL, check_out DATE NOT NULL, num_guests INTEGER NOT NULL CHECK(num_guests > 0), breakfast BOOLEAN NOT NULL DEFAULT 0, notes TEXT, CHECK (date(check_out) > date(check_in)), FOREIGN KEY (room_id) REFERENCES rooms(room_id) );