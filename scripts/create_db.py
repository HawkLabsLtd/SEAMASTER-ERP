import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def create_database():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("DATABASE_URL is not set.")
        return

    result = urlparse(db_url)
    username = result.username
    password = result.password
    target_db = result.path[1:]
    hostname = result.hostname
    port = result.port
    
    print(f"Attempting to create database '{target_db}'...")
    
    # Connect to default 'postgres' database to create the new one
    try:
        conn = psycopg2.connect(
            database='postgres',
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Check if exists
        cur.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{target_db}'")
        exists = cur.fetchone()
        
        if not exists:
            cur.execute(f"CREATE DATABASE {target_db}")
            print(f"Database '{target_db}' created successfully!")
        else:
            print(f"Database '{target_db}' already exists.")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Failed to create database: {e}")

if __name__ == "__main__":
    create_database()
