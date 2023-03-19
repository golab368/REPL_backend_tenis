import unittest
import json
import datetime
from tennis_reservation import TennisCourt
from dateutil.relativedelta import relativedelta, MO
from unittest.mock import patch


class TestTennisCourt(unittest.TestCase):
    def setUp(self):
        self.db_config = {
            "dbname": "tennis_court_db",
            "user": "m",  # <your_mac_username>
            "password": "",
            "host": "localhost",
            "port": "5432",
        }
        self.tc = TennisCourt(self.db_config)
        self.tc.clean_database()

    def test_create_table(self):
        self.assertIn("reservations", self.tc.get_all_tables())

    def test_make_reservation(self):
        result, message = self.tc.make_reservation(
            "Milosz", datetime.datetime(2023, 3, 25, 15, 0), 60
        )
        self.assertTrue(result)
        self.assertIn("Reservation made successfully", message)

    def test_make_reservation_invalid_duration(self):
        result, message = self.tc.make_reservation(
            "Milosz", datetime.datetime(2023, 3, 25, 15, 0), 45
        )
        self.assertFalse(result)
        self.assertIn("Invalid duration", message)

    def test_make_reservation_too_close(self):
        result, message = self.tc.make_reservation(
            "Milosz", datetime.datetime.now() + datetime.timedelta(minutes=30), 60
        )
        self.assertFalse(result)
        self.assertIn("The date must be at least one hour from now", message)

    def test_cancel_reservation(self):
        reservation_date = datetime.datetime.now() + datetime.timedelta(hours=2)
        success, message = self.tc.make_reservation("Milosz", reservation_date, 30)
        self.assertTrue(success)

        with patch("builtins.input", return_value="1"):
            success, message = self.tc.cancel_reservation("Milosz")
            self.assertTrue(success)
            self.assertIn("has been canceled", message)

    def test_cancel_reservation_no_reservations(self):
        result, message = self.tc.cancel_reservation("Bob")
        self.assertFalse(result)
        self.assertIn("No reservations found", message)

    def test_save_schedule_to_json(self):
        self.tc.make_reservation("Milosz", datetime.datetime(2023, 3, 25, 15, 0), 60)
        self.tc.save_schedule(
            datetime.datetime(2023, 3, 25),
            datetime.datetime(2023, 3, 25),
            "json",
            "test_schedule.json",
        )

        with open("test_schedule.json", "r") as infile:
            data = json.load(infile)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["name"], "Milosz")

    def test_make_reservation_conflict(self):
        reservation_date = datetime.datetime.now() + datetime.timedelta(hours=2)
        self.tc.make_reservation("Milosz", reservation_date, 30)
        success, message = self.tc.make_reservation("Bob", reservation_date, 30)
        self.assertFalse(success)
        self.assertIn("Requested time slot is not available", message)

    def test_make_reservation_too_many_in_one_week(self):
        start_date = datetime.datetime.now()
        reservation_date1 = start_date + relativedelta(weekday=MO)

        reservation_date2 = reservation_date1 + datetime.timedelta(days=1)
        reservation_date3 = reservation_date1 + datetime.timedelta(days=2)

        self.tc.make_reservation("Milosz", reservation_date1, 30)
        self.tc.make_reservation("Milosz", reservation_date2, 30)

        message = self.tc.make_reservation("Milosz", reservation_date3, 30)

        self.assertIn(
            "You have already made two reservations this week. No more reservations are allowed.",
            message,
        )

    def tearDown(self):
        self.tc.clean_database()


if __name__ == "__main__":
    unittest.main()
