import os
import psycopg2
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def test_connection():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("DATABASE_URL is not set.")
        return

    print(f"Testing connection to: {db_url}")
    try:
        result = urlparse(db_url)
        username = result.username
        password = result.password
        database = result.path[1:]
        hostname = result.hostname
        port = result.port
        
        conn = psycopg2.connect(
            database=database,
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        print("Successfully connected to PostgreSQL!")
        conn.close()
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_connection()
