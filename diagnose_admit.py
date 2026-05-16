"""Diagnose admit button issues."""
import xmlrpc.client

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USER, PASSWORD, {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

# Check wards
wards = models.execute_kw(DB, uid, PASSWORD, "health.ward", "search_read",
    [[]], {"fields": ["id", "name", "ward_type", "doctor_ids"]})
print(f"\n=== Wards ({len(wards)}) ===")
for w in wards:
    docs = w["doctor_ids"]
    print(f"  ID:{w['id']} | {w['name']:25s} | Type: {w['ward_type']:15s} | Doctors: {docs}")

# Check patients
patients = models.execute_kw(DB, uid, PASSWORD, "health.patient", "search_read",
    [[]], {"fields": ["id", "name", "admission_status", "ward_id", "ai_recommended_ward_id"]})
print(f"\n=== Patients ({len(patients)}) ===")
for p in patients:
    ward = p["ward_id"][1] if p["ward_id"] else "None"
    ai_ward = p["ai_recommended_ward_id"][1] if p["ai_recommended_ward_id"] else "None"
    print(f"  ID:{p['id']} | {p['name']:25s} | Status: {p['admission_status']:12s} | Ward: {ward} | AI Ward: {ai_ward}")

# Check doc@test.com user ID
doc_user = models.execute_kw(DB, uid, PASSWORD, "res.users", "search_read",
    [[["login", "=", "doc@test.com"]]], {"fields": ["id", "name", "groups_id"]})
if doc_user:
    print(f"\n=== doc@test.com ===")
    print(f"  ID: {doc_user[0]['id']}")
    print(f"  Groups: {doc_user[0]['groups_id']}")
