"""Create nurse user accounts."""
import xmlrpc.client

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USER, PASSWORD, {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

# Get the nurse group ID
nurse_groups = models.execute_kw(DB, uid, PASSWORD, "res.groups", "search_read",
    [[["full_name", "like", "Nurse"]]], {"fields": ["id", "full_name"]})
nurse_group_id = nurse_groups[0]["id"] if nurse_groups else None
print(f"Nurse group: {nurse_groups}")

if not nurse_group_id:
    print("ERROR: Nurse group not found!")
    exit(1)

# Create 2 nurse accounts
nurses = [
    {"name": "Nurse Emma Johnson", "login": "emma.johnson@hospital.local"},
    {"name": "Nurse David Park", "login": "david.park@hospital.local"},
]

for n in nurses:
    # Check if already exists
    existing = models.execute_kw(DB, uid, PASSWORD, "res.users", "search",
        [[["login", "=", n["login"]]]])
    if existing:
        print(f"  Already exists: {n['login']}")
        continue

    user_id = models.execute_kw(DB, uid, PASSWORD, "res.users", "create", [{
        "name": n["name"],
        "login": n["login"],
        "password": "admin",
        "groups_id": [(4, nurse_group_id)],
    }])
    print(f"  Created: {n['login']} (ID: {user_id})")

print("\nDone! Nurse accounts ready.")
print("Password for all: admin")
