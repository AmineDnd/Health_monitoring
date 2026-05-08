import psycopg2
try:
    conn = psycopg2.connect(host='localhost', port=5432, user='openpg', password='openpgpwd', dbname='postgres')
    cur = conn.cursor()
    cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname")
    dbs = [r[0] for r in cur.fetchall()]
    print("Available databases:", dbs)
    conn.close()
except Exception as e:
    print("Error:", e)
