import csv
import datetime
import json
import psycopg2


class TennisCourt:
    def __init__(self, db_config):
        self.conn = psycopg2.connect(
            dbname=db_config["dbname"],
            user=db_config["user"],
            password=db_config["password"],
            host=db_config["host"],
            port=db_config["port"],
        )
        self._create_table()

    def _create_table(self):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS reservations (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    date DATE NOT NULL,
                    start_time TIME NOT NULL,
                    end_time TIME NOT NULL
                )
            """
            )
            self.conn.commit()

    def _find_closest_available_time(self, date, duration):
        current_time = date.time()
        duration_delta = datetime.timedelta(minutes=duration)

        while True:
            next_start_time, next_end_time, _ = self._get_next_reservation(date)
            if next_start_time is None:
                # No more reservations for the day
                if date + duration_delta <= date.replace(hour=23, minute=59):
                    return (
                        current_time,
                        (
                            datetime.datetime.combine(date.date(), current_time)
                            + duration_delta
                        ).time(),
                    )
                else:
                    return None, None

            available_duration = (
                datetime.datetime.combine(date.date(), next_start_time)
                - datetime.datetime.combine(date.date(), current_time)
                - datetime.timedelta(minutes=1)
            )
            if available_duration >= duration_delta:
                return (
                    current_time,
                    (
                        datetime.datetime.combine(date.date(), current_time)
                        + duration_delta
                    ).time(),
                )

            current_time = next_end_time
            date = datetime.datetime.combine(date.date(), current_time)

    def _get_next_reservation(self, date):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT start_time, end_time, name
                FROM reservations
                WHERE date = %s AND start_time >= %s
                ORDER BY start_time
                LIMIT 1
                """,
                (date.date(), date.time()),
            )
            next_reservation = cur.fetchone()

        if next_reservation:
            start_time, end_time, name = next_reservation
            return start_time, end_time, name
        else:
            return None, None, None

    def make_reservation(self, name, date, duration):

        if duration not in [30, 60, 90]:
            return (
                False,
                "Invalid duration. Please choose either 30, 60, or 90 minutes.",
            )

        if date <= datetime.datetime.now() + datetime.timedelta(hours=1):
            return False, "The date must be at least one hour from now"

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT start_time, end_time
                FROM reservations
                WHERE date = %s AND (
                    (start_time >= %s AND start_time < %s + interval '%s minutes') OR
                    (end_time > %s AND end_time <= %s + interval '%s minutes') OR
                    (start_time <= %s AND end_time >= %s + interval '%s minutes') OR
                    (start_time <= %s AND end_time >= %s)
                )
                """,
                (
                    date.date(),
                    date.time(),
                    date.time(),
                    duration,
                    date.time(),
                    date.time(),
                    duration,
                    date.time(),
                    date.time(),
                    duration,
                    date.time(),
                    date.time(),
                ),
            )
            conflicting_reservation = cur.fetchone()

            if conflicting_reservation:

                start_time, end_time = self._find_closest_available_time(date, duration)
                if start_time is None or end_time is None:
                    return False, "No available time slots for the requested duration."
                else:
                    return (
                        False,
                        f"Requested time slot is not available. The closest available time slot is from {start_time} to {end_time}.",
                    )

            # Check if the user already has two reservations
            week_start = date - datetime.timedelta(days=date.weekday())
            week_end = week_start + datetime.timedelta(days=5)
            cur.execute(
                """
                SELECT COUNT(*)
                FROM reservations
                WHERE name = %s AND date >= %s AND date <= %s
                """,
                (name, week_start.date(), week_end.date()),
            )
            user_reservation_count = cur.fetchone()[0]

            if user_reservation_count >= 2:

                return (
                    False,
                    "You have already made two reservations this week. No more reservations are allowed.",
                )

            # The desired time slot is available
            end_time = (
                datetime.datetime.combine(date.date(), date.time())
                + datetime.timedelta(minutes=duration)
            ).time()
            cur.execute(
                """
                INSERT INTO reservations (name, date, start_time, end_time)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (name, date.date(), date.time(), end_time),
            )
            reservation_id = cur.fetchone()[0]
            self.conn.commit()

        return True, f"Reservation made successfully with ID {reservation_id}."

    def cancel_reservation(self, name):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT date, start_time, end_time
                FROM reservations
                WHERE name = %s
                ORDER BY date, start_time
            """,
                (name,),
            )
            reservations = cur.fetchall()

        if not reservations:
            return False, f"No reservations found for {name}"

        print(f"Reservations for {name}:")
        for idx, (date, start_time, end_time) in enumerate(reservations, 1):
            print(f"{idx}. {date} {start_time} - {end_time}")

        selected_index = int(
            input("Enter the number of the reservation you want to cancel: ")
        )
        if 1 <= selected_index <= len(reservations):
            date, start_time = reservations[selected_index - 1][:2]

            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM reservations
                    WHERE name = %s AND date = %s AND start_time = %s
                    RETURNING end_time
                """,
                    (name, date, start_time),
                )
                deleted_reservation = cur.fetchone()
                self.conn.commit()

            if deleted_reservation:
                end_time = deleted_reservation[0]
                return (
                    True,
                    f"Reservation for {name} on {date} from {start_time} to {end_time} has been canceled",
                )
        else:
            return False, "Invalid selection"

    def print_schedule(self, start_date, end_date):
        date = start_date
        any_reservations = False

        while date <= end_date:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT start_time, end_time, name
                    FROM reservations
                    WHERE date = %s
                    ORDER BY start_time
                """,
                    (date.date(),),
                )
                reservations = cur.fetchall()

            if reservations:
                any_reservations = True
                print(date.strftime("%A, %Y-%m-%d:"))
                for start_time, end_time, name in reservations:
                    print(
                        f" {name} on {date.strftime('%A, %Y-%m-%d')} at {start_time} - {end_time}"
                    )
            date += datetime.timedelta(days=1)

        if not any_reservations:
            print("No Reservations")

    def save_schedule(self, start_date, end_date, file_format, file_name):
        data = []
        date = start_date
        while date <= end_date:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT name, start_time, end_time
                    FROM reservations
                    WHERE date = %s
                    ORDER BY start_time
                """,
                    (date.date(),),
                )
                reservations = cur.fetchall()

            for name, start_time, end_time in reservations:
                data.append(
                    {
                        "name": name,
                        "start_time": start_time,
                        "end_time": end_time,
                        "date": date.date(),
                    }
                )

            date += datetime.timedelta(days=1)

        if file_format == "json":
            with open(file_name, "w") as outfile:
                json.dump(data, outfile, default=str)
        elif file_format == "csv":
            with open(file_name, "w") as outfile:
                writer = csv.DictWriter(
                    outfile, fieldnames=["name", "start_time", "end_time", "date"]
                )
                writer.writeheader()
                writer.writerows(data)

    def get_all_tables(self):
        with self.conn.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';"
            )
            tables = [table[0] for table in cursor.fetchall()]
        return tables

    def clean_database(self):
        with self.conn.cursor() as cursor:
            tables = self.get_all_tables()
            for table in tables:
                cursor.execute(f"DELETE FROM {table};")
            self.conn.commit()


if __name__ == "__main__":
    db_config = {
        "dbname": "tennis_court_db",
        "user": "m",  # your pc username
        "password": "",
        "host": "localhost",
        "port": "5432",
    }

    tennis_court = TennisCourt(db_config)
    tennis_court.clean_database()
    start_date = None
    end_date = None

    def get_valid_input(prompt, format):
        while True:
            user_input = input(prompt)
            try:
                valid_input = datetime.datetime.strptime(user_input, format)
                return valid_input
            except ValueError:
                print(f"Invalid input. Please enter the correct format ({format}).")

    while True:
        print("Please choose an option:")
        print("1. Make a reservation")
        print("2. Cancel a reservation")
        print("3. Print schedule")
        print("4. Save schedule to file")
        print("5. Exit")

        choice = input("Enter the number of your choice: ")

        if choice == "1":
            name = input("Enter your name: ")
            date_obj = get_valid_input(
                "Enter the reservation date (YYYY-MM-DD): ", "%Y-%m-%d"
            )
            time_obj = get_valid_input("Enter the reservation time (HH:MM): ", "%H:%M")

            while True:
                duration = int(input("Enter the duration in minutes (30, 60, or 90): "))
                if duration in (30, 60, 90):
                    break
                else:
                    print(
                        "Invalid duration. Please choose either 30, 60, or 90 minutes."
                    )

            reservation_date = datetime.datetime.combine(
                date_obj.date(), time_obj.time()
            )
            success, message = tennis_court.make_reservation(
                name, reservation_date, duration
            )
            print(message)

            if success:
                if start_date is None or reservation_date.date() < start_date.date():
                    start_date = reservation_date
                if end_date is None or reservation_date.date() > end_date.date():
                    end_date = reservation_date

        elif choice == "2":
            name = input("Enter your name: ")
            success, message = tennis_court.cancel_reservation(name)
            print(message)

        elif choice == "3":
            if start_date and end_date:
                tennis_court.print_schedule(start_date, end_date)
            else:
                print("No reservations have been made yet.")

        elif choice == "4":
            if start_date and end_date:
                file_format = input("Enter the file format (json or csv): ").lower()
                file_name = input("Enter the file name (without the extension): ")

                if file_format == "json":
                    file_name += ".json"
                elif file_format == "csv":
                    file_name += ".csv"
                else:
                    print("Invalid file format. Please try again.")
                    continue

                tennis_court.save_schedule(start_date, end_date, file_format, file_name)
                print(f"Schedule saved to {file_name}")
            else:
                print("No reservations have been made yet.")

        elif choice == "5":
            print("Goodbye!")
            break

        else:
            print("Invalid option. Please try again.")
