import xmlrpc.client, sys

URL = "http://localhost:8069"
DB  = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

print("=== SmartLab — Wipe Clinical Data ===\n")

common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
uid = common.authenticate(DB, USER, PASSWORD, {})
if not uid:
    print("Auth failed — wrong password?"); sys.exit(1)
print(f"Logged in as admin (uid={uid})\n")

models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

def count(model):
    return models.execute_kw(DB, uid, PASSWORD, model, 'search_count', [[]])

def wipe(model, label):
    ids = models.execute_kw(DB, uid, PASSWORD, model, 'search', [[]])
    if ids:
        models.execute_kw(DB, uid, PASSWORD, model, 'unlink', [ids])
        print(f"  Deleted {len(ids):>5} {label}")
    else:
        print(f"  No {label} to delete")

# Order matters — delete children before parents
print("Wiping clinical data...")
wipe('health.alert',        'alerts')
wipe('health.vital.record', 'vital records')
wipe('health.handoff',      'handoff records')
wipe('health.patient',      'patients')

print("\nWipe complete. System is fresh — no patients, vitals, or alerts remain.")
print(f"\nOpen: http://localhost:8069")
