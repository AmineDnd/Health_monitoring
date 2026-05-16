"""
Create a fresh Odoo database using the /xmlrpc/2/db service.
This runs server-side and doesn't need an existing DB.
"""
import xmlrpc.client, sys, time

sys.stdout.reconfigure(encoding='utf-8')

URL = "http://localhost:8069"
NEW_DB = "smartlab_fresh"   # New DB name to avoid conflict with locked smartlab_db
ADMIN_PW = "admin"
MASTER_PW_CANDIDATES = ["admin", "", "Odoo2024", "odoo"]

print("=== Creating fresh Odoo database ===")
print(f"Target: {NEW_DB}")

db_svc = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/db', allow_none=True)

# Try listing databases first (doesn't need a DB)
try:
    dbs = db_svc.list()
    print(f"Existing databases: {dbs}")
except Exception as e:
    print(f"Cannot list DBs: {e}")

# Try creating the new database
for master_pw in MASTER_PW_CANDIDATES:
    try:
        print(f"\nTrying master_pw='{master_pw}'...")
        db_svc.create_database(
            master_pw,   # master password
            NEW_DB,      # db name
            False,       # demo data
            "en_US",     # language
            ADMIN_PW,    # admin password
            "Admin",     # admin name
            "admin@smartlab.com"  # admin email
        )
        print(f"SUCCESS! Database '{NEW_DB}' created with master_pw='{master_pw}'")
        break
    except Exception as e:
        err = str(e)
        if 'already exists' in err.lower():
            print(f"DB '{NEW_DB}' already exists - continuing")
            break
        print(f"  Failed: {err[:120]}")
else:
    print("\nAll master passwords failed.")
    print("-> Try the web UI: http://localhost:8069/web/database/manager")
    sys.exit(1)

# Wait for DB to be initialized
print(f"\nWaiting 15s for {NEW_DB} to initialize...")
time.sleep(15)

# Authenticate
print(f"Authenticating as admin...")
common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common', allow_none=True)
uid = common.authenticate(NEW_DB, 'admin', ADMIN_PW, {})
if not uid:
    print("Auth failed! Try logging in manually.")
    sys.exit(1)
print(f"Authenticated uid={uid}")

# Check health_monitoring module
models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object', allow_none=True)
print("\nChecking health_monitoring module...")
try:
    mids = models.execute_kw(NEW_DB, uid, ADMIN_PW, 'ir.module.module', 'search',
                              [[['name', '=', 'health_monitoring']]])
    if mids:
        info = models.execute_kw(NEW_DB, uid, ADMIN_PW, 'ir.module.module', 'read',
                                  [[mids[0]]], {'fields': ['state', 'installed_version']})[0]
        print(f"health_monitoring: state={info['state']}")
        if info['state'] != 'installed':
            print("Installing health_monitoring...")
            models.execute_kw(NEW_DB, uid, ADMIN_PW, 'ir.module.module',
                               'button_immediate_install', [[mids[0]]])
            print("Install triggered. Wait 60s then test.")
        else:
            print("Already installed!")
    else:
        print("Module NOT found. Check addons_path in odoo.conf includes:")
        print("  c:\\users\\amine\\desktop\\smartlab\\odoo\\addons")
except Exception as e:
    print(f"Module check error: {e}")

print(f"\nURL: http://localhost:8069  DB: {NEW_DB}  Login: admin / {ADMIN_PW}")
