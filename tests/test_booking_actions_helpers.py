import unittest
from datetime import date

from actions.actions import (
    find_available_rooms,
    normalize_guest_count,
    parse_booking_date_range,
)


class TestBookingHelpers(unittest.TestCase):
    def test_parse_range_iso(self) -> None:
        check_in, check_out = parse_booking_date_range("2025-11-20 to 2025-11-22")
        self.assertEqual(check_in, date(2025, 11, 20))
        self.assertEqual(check_out, date(2025, 11, 22))

    def test_parse_single_iso(self) -> None:
        check_in, check_out = parse_booking_date_range("2025-11-20")
        self.assertEqual(check_in, date(2025, 11, 20))
        self.assertEqual(check_out, date(2025, 11, 21))

    def test_negative_guests_raises(self) -> None:
        with self.assertRaises(ValueError):
            normalize_guest_count(-1)

    def test_fractional_guests_raises(self) -> None:
        with self.assertRaises(ValueError):
            normalize_guest_count(1.5)

    def test_find_available_rooms_excludes_booked_room(self) -> None:
        """Room 1 is booked between 2025-11-05 and 2025-11-12 in the seed data.

        For a 2-guest booking overlapping that interval, room 1 should not
        appear in the availability results.
        """

        check_in = date(2025, 11, 6)
        check_out = date(2025, 11, 8)
        rooms = find_available_rooms(2, check_in, check_out)

        # All returned rooms should be able to host at least 2 guests
        self.assertTrue(all(room["capacity"] >= 2 for room in rooms))
        # And room_id 1 should not be offered for this interval
        self.assertTrue(all(room["room_id"] != 1 for room in rooms))


if __name__ == "__main__":  # pragma: no cover - manual execution
    unittest.main()
