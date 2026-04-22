import sys
import os
from sqlalchemy import create_engine, text

# Add backend directory to path
sys.path.append(os.path.abspath('backend'))

from config import settings

def run_migration():
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        print("Adding seat_numbers and seat_preference columns...")
        # Check if columns exist first (optional but safer)
        try:
            conn.execute(text("ALTER TABLE bookings ADD COLUMN seat_numbers VARCHAR(255) NULL"))
            print("Added seat_numbers")
        except Exception as e:
            print(f"seat_numbers probably already exists or error: {e}")
            
        try:
            conn.execute(text("ALTER TABLE bookings ADD COLUMN seat_preference VARCHAR(50) NULL"))
            print("Added seat_preference")
        except Exception as e:
            print(f"seat_preference probably already exists or error: {e}")
        
        conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    run_migration()
