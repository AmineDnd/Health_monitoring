"""Create doc@test.com account."""
import xmlrpc.client

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USER, PASSWORD, {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

# Get doctor group
doc_groups = models.execute_kw(DB, uid, PASSWORD, "res.groups", "search_read",
    [[["full_name", "like", "Doctor"]]], {"fields": ["id"]})
doc_gid = doc_groups[0]["id"]

existing = models.execute_kw(DB, uid, PASSWORD, "res.users", "search",
    [[["login", "=", "doc@test.com"]]])

if existing:
    print("Already exists!")
else:
    uid_new = models.execute_kw(DB, uid, PASSWORD, "res.users", "create", [{
        "name": "Doctor",
        "login": "doc@test.com",
        "password": "admin",
        "groups_id": [(4, doc_gid)],
    }])
    print(f"Created: doc@test.com (ID: {uid_new})")

print("Login: doc@test.com | Password: admin")
