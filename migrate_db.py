import os
import sys

from sqlalchemy import create_engine

sys.path.append(os.path.abspath("backend"))

from config import settings
from services.schema_service import upgrade_runtime_schema


def run_migration() -> None:
    engine = create_engine(settings.database_url)
    upgrade_runtime_schema(engine)
    print("Database migration complete.")


if __name__ == "__main__":
    run_migration()
