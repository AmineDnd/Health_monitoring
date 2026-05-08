import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

print("=== Dropping health_monitor database ===")
try:
    conn = psycopg2.connect(
        host='localhost', port=5432,
        user='openpg', password='openpgpwd',
        dbname='postgres'
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    # Terminate all active connections to the database first
    cur.execute("""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = 'health_monitor' AND pid <> pg_backend_pid()
    """)
    terminated = cur.rowcount
    print(f"Terminated {terminated} active connection(s).")

    cur.execute("DROP DATABASE IF EXISTS health_monitor")
    print("Database 'health_monitor' dropped successfully.")
    conn.close()

except Exception as e:
    print(f"Error: {e}")
