import os
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv
from contextlib import contextmanager

# Load environment variables
load_dotenv()

# Database configuration from environment variables
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "railway_booking")

# Initialize MySQL connection pool
try:
    db_pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="railway_pool",
        pool_size=5,
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    print(f"Connected to database: {DB_NAME} at {DB_HOST}:{DB_PORT}")
except mysql.connector.Error as err:
    print(f"Error creating connection pool: {err}")
    db_pool = None

@contextmanager
def get_connection():
    """Context manager for database connections from the pool."""
    if not db_pool:
        raise Exception("Database connection pool not initialized")
    
    conn = db_pool.get_connection()
    try:
        yield conn
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
