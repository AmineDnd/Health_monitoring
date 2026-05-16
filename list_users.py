import xmlrpc.client
URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"
common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USER, PASSWORD, {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")
users = models.execute_kw(DB, uid, PASSWORD, "res.users", "search_read",
    [[["active", "=", True]]], {"fields": ["login", "name"]})
print("\n=== Available Login Accounts ===\n")
for u in users:
    login = u["login"]
    name = u["name"]
    print(f"  Login: {login:30s} | Name: {name}")
print(f"\n  Total: {len(users)} accounts")
print("  Password for all: admin")
