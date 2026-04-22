from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import Train


def seed_default_trains(db: Session) -> int:
    base_schedule = [
        ("Rajdhani Express", "Surat", "Mumbai", "07:00", "11:30", 2200),
        ("Duronto Express", "Surat", "Mumbai", "09:30", "13:50", 1800),
        ("Double Decker", "Surat", "Mumbai", "14:15", "18:30", 1600),
        ("Garib Rath", "Surat", "Mumbai", "22:10", "03:40", 1300),
        ("Intercity Superfast", "Surat", "Gandhinagar", "06:45", "12:10", 1450),
        ("Jan Shatabdi", "Surat", "Gandhinagar", "16:20", "21:30", 1250),
        ("Shatabdi Express", "Mumbai", "Delhi", "06:00", "16:30", 4400),
        ("Rajdhani Express", "Mumbai", "Delhi", "17:15", "06:00", 5100),
        ("Tejas Express", "Ahmedabad", "Mumbai", "08:00", "14:20", 2400),
        ("Vande Bharat", "Ahmedabad", "Mumbai", "15:30", "21:20", 2800),
        ("Intercity Express", "Ahmedabad", "Surat", "10:10", "13:05", 900),
        ("Superfast Express", "Delhi", "Jaipur", "07:30", "12:00", 1200),
    ]

    inserted = 0
    start_date = date.today() + timedelta(days=1)

    for day_offset in range(7):
        travel_date = start_date + timedelta(days=day_offset)
        for train_name, source, destination, departure_time, arrival_time, fare in base_schedule:
            exists = (
                db.query(Train)
                .filter(
                    Train.train_name == train_name,
                    Train.source == source,
                    Train.destination == destination,
                    Train.travel_date == travel_date,
                    Train.departure_time == departure_time,
                )
                .first()
            )
            if exists:
                continue

            seats = 70 + ((day_offset * 11 + len(train_name)) % 90)
            db.add(
                Train(
                    train_name=train_name,
                    source=source,
                    destination=destination,
                    travel_date=travel_date,
                    departure_time=departure_time,
                    arrival_time=arrival_time,
                    seats_available=seats,
                    fare_per_seat=fare,
                )
            )
            inserted += 1

    if inserted:
        db.commit()
    return inserted
