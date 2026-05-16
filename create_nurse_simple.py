"""Create nurse@test.com account."""
import xmlrpc.client

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USER, PASSWORD, {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

# Get nurse group
nurse_groups = models.execute_kw(DB, uid, PASSWORD, "res.groups", "search_read",
    [[["full_name", "like", "Nurse"]]], {"fields": ["id"]})
nurse_gid = nurse_groups[0]["id"]

# Check if exists
existing = models.execute_kw(DB, uid, PASSWORD, "res.users", "search",
    [[["login", "=", "nurse@test.com"]]])

if existing:
    print("Already exists!")
else:
    uid_new = models.execute_kw(DB, uid, PASSWORD, "res.users", "create", [{
        "name": "Nurse",
        "login": "nurse@test.com",
        "password": "admin",
        "groups_id": [(4, nurse_gid)],
    }])
    print(f"Created: nurse@test.com (ID: {uid_new})")

print("Login: nurse@test.com | Password: admin")
