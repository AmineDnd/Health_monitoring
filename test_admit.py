"""Test admit buttons to find exact error."""
import xmlrpc.client, traceback

URL = "http://localhost:8069"
DB = "smartlab_db"

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

# Test as admin first
print("=== Testing as ADMIN ===")
uid = common.authenticate(DB, "admin", "admin", {})

# Test action_admit on patient 37
try:
    result = models.execute_kw(DB, uid, "admin", "health.patient", "action_admit", [[37]])
    print(f"  action_admit: OK -> {result}")
except Exception as e:
    print(f"  action_admit FAILED: {e}")

# Reset back to triage for next test
try:
    models.execute_kw(DB, uid, "admin", "health.patient", "write", [[37], {"admission_status": "triage"}])
    print("  Reset to triage: OK")
except Exception as e:
    print(f"  Reset FAILED: {e}")

# Test action_admit_ai
try:
    result = models.execute_kw(DB, uid, "admin", "health.patient", "action_admit_ai", [[37]])
    print(f"  action_admit_ai: OK -> {result}")
except Exception as e:
    print(f"  action_admit_ai FAILED: {e}")

# Reset
try:
    models.execute_kw(DB, uid, "admin", "health.patient", "write", [[37], {"admission_status": "triage", "ward_id": 3}])
    print("  Reset to triage+General: OK")
except Exception as e:
    print(f"  Reset FAILED: {e}")

# Test as doc@test.com
print("\n=== Testing as DOC ===")
doc_uid = common.authenticate(DB, "doc@test.com", "admin", {})

try:
    result = models.execute_kw(DB, doc_uid, "admin", "health.patient", "action_admit", [[37]])
    print(f"  action_admit: OK -> {result}")
except Exception as e:
    print(f"  action_admit FAILED: {e}")

# Reset
models.execute_kw(DB, uid, "admin", "health.patient", "write", [[37], {"admission_status": "triage", "ward_id": 3}])

try:
    result = models.execute_kw(DB, doc_uid, "admin", "health.patient", "action_admit_ai", [[37]])
    print(f"  action_admit_ai: OK -> {result}")
except Exception as e:
    print(f"  action_admit_ai FAILED: {e}")

# Test as nurse
print("\n=== Testing as NURSE ===")
nurse_uid = common.authenticate(DB, "nurse@test.com", "admin", {})

# Reset
models.execute_kw(DB, uid, "admin", "health.patient", "write", [[37], {"admission_status": "triage", "ward_id": 3}])

try:
    result = models.execute_kw(DB, nurse_uid, "admin", "health.patient", "action_admit", [[37]])
    print(f"  action_admit: OK -> {result}")
except Exception as e:
    print(f"  action_admit FAILED: {e}")
