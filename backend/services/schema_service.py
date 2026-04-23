from sqlalchemy import inspect, text


BOOKING_COLUMNS = {
    "train_number": "ALTER TABLE bookings ADD COLUMN train_number VARCHAR(50) NULL",
    "train_name": "ALTER TABLE bookings ADD COLUMN train_name VARCHAR(100) NULL",
    "source": "ALTER TABLE bookings ADD COLUMN source VARCHAR(60) NULL",
    "destination": "ALTER TABLE bookings ADD COLUMN destination VARCHAR(60) NULL",
    "departure_time": "ALTER TABLE bookings ADD COLUMN departure_time VARCHAR(20) NULL",
    "arrival_time": "ALTER TABLE bookings ADD COLUMN arrival_time VARCHAR(20) NULL",
    "data_source": "ALTER TABLE bookings ADD COLUMN data_source VARCHAR(20) NULL",
}


def _has_table(engine, table_name: str) -> bool:
    return table_name in inspect(engine).get_table_names()


def _column_names(engine, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def upgrade_runtime_schema(engine) -> None:
    if not _has_table(engine, "bookings"):
        return

    with engine.begin() as conn:
        booking_columns = _column_names(engine, "bookings")
        for column_name, statement in BOOKING_COLUMNS.items():
            if column_name not in booking_columns:
                conn.execute(text(statement))

        dialect_name = engine.dialect.name
        has_trains_table = _has_table(engine, "trains")

        if has_trains_table and dialect_name == "mysql":
            conn.execute(
                text(
                    """
                    UPDATE bookings b
                    LEFT JOIN trains t ON b.train_id = t.id
                    SET
                        b.train_number = COALESCE(b.train_number, CAST(t.id AS CHAR)),
                        b.train_name = COALESCE(b.train_name, t.train_name),
                        b.source = COALESCE(b.source, t.source),
                        b.destination = COALESCE(b.destination, t.destination),
                        b.departure_time = COALESCE(b.departure_time, t.departure_time),
                        b.arrival_time = COALESCE(b.arrival_time, t.arrival_time),
                        b.data_source = COALESCE(b.data_source, 'database')
                    """
                )
            )

            for foreign_key in inspect(engine).get_foreign_keys("bookings"):
                if foreign_key.get("referred_table") != "trains" or not foreign_key.get("name"):
                    continue
                conn.execute(text(f"ALTER TABLE bookings DROP FOREIGN KEY {foreign_key['name']}"))

            conn.execute(text("ALTER TABLE bookings MODIFY COLUMN train_id INT NULL"))
            conn.execute(text("DELETE FROM trains"))

        conn.execute(
            text(
                """
                UPDATE bookings
                SET data_source = COALESCE(data_source, 'api')
                WHERE data_source IS NULL OR data_source = ''
                """
            )
        )
