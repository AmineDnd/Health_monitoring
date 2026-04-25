import xmlrpc.client
import sys

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

def main():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        uid = common.authenticate(DB, USER, PASSWORD, {})
        if not uid:
            print("Auth failed")
            return

        wards = models.execute_kw(DB, uid, PASSWORD, 'health.ward', 'search_read',
            [[]], {'fields': ['name', 'ward_type', 'capacity', 'current_occupancy', 'floor_number']}
        )
        print(f"--- Loaded {len(wards)} Wards ---")
        for w in wards:
            print(f"[{w.get('ward_type')}] {w.get('name')} | Capacity: {w.get('current_occupancy')}/{w.get('capacity')} | Floor: {w.get('floor_number')}")

        doctors = models.execute_kw(DB, uid, PASSWORD, 'res.users', 'search_read',
            [[['login', 'like', '@hospital.local']]], {'fields': ['name', 'login']}
        )
        print(f"\n--- Loaded {len(doctors)} Demo Doctors ---")
        for d in doctors:
            print(f"- {d.get('name')} ({d.get('login')})")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
