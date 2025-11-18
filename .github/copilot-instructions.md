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


