"""Verify that new security rules exist in the database."""
import xmlrpc.client

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USER, PASSWORD, {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

# Check all custom rules
rules = models.execute_kw(DB, uid, PASSWORD, "ir.rule", "search_read",
    [[["model_id.model", "in", ["health.alert", "health.vital.record", "mail.message"]]]],
    {"fields": ["name", "model_id", "domain_force"]})

print(f"\n=== Found {len(rules)} security rules ===\n")
for r in rules:
    model = r["model_id"][1] if r["model_id"] else "?"
    print(f"  [{model:30s}] {r['name']}")

# Verify specific rules we expect
expected = [
    "Doctor Ward Alerts",
    "Admin/Nurse All Alerts", 
    "Doctor Ward Vitals",
    "Admin/Nurse All Vitals",
    "Own Messages Only (Write/Delete)",
    "Admin Full Message Access",
]
found_names = [r["name"] for r in rules]
print("\n=== Verification ===")
all_ok = True
for name in expected:
    ok = name in found_names
    status = "OK" if ok else "MISSING"
    print(f"  [{status}] {name}")
    if not ok:
        all_ok = False

if all_ok:
    print("\nAll security rules created successfully!")
else:
    print("\nSome rules are MISSING - may need a fresh install or manual creation.")
