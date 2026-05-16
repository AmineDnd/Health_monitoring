import xmlrpc.client, sys, time

URL = "http://localhost:8069"
DB  = "health_monitor"
ADMIN_PW = "admin"

print("=== SmartLab Fresh Database Setup ===\n")
print(f"[1] Creating database '{DB}'...")
try:
    db_svc = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/db')
    for mpw in ['admin', 'odoo', '', 'Odoo2024']:
        try:
            db_svc.create_database(mpw, DB, False, 'en_US', ADMIN_PW, 'Admin', 'admin@smartlab.com')
            print(f"   OK: database created (master_pw='{mpw}')")
            break
        except Exception as e:
            err = str(e)
            if 'already exists' in err:
                print("   OK: database already exists")
                break
            print(f"   try '{mpw}': {err[:80]}")
    else:
        print("   CANNOT create db via XML-RPC")
        print("   -> Go to http://localhost:8069/web/database/manager")
        print("      Create DB: health_monitor  Admin pw: admin  Lang: English")
        sys.exit(1)
except Exception as e:
    print(f"   connect error: {e}"); sys.exit(1)

print("\n[2] Authenticating...")
time.sleep(5)
common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
uid = common.authenticate(DB, 'admin', ADMIN_PW, {})
if not uid:
    print("   FAIL: wrong credentials"); sys.exit(1)
print(f"   OK uid={uid}")

models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
print("\n[3] Looking for health_monitoring module...")
mids = models.execute_kw(DB, uid, ADMIN_PW, 'ir.module.module', 'search', [[['name','=','health_monitoring']]])
if not mids:
    print("   NOT FOUND - addons_path is wrong.")
    print("   odoo.conf must include: c:\\users\\amine\\desktop\\smartlab\\odoo\\addons")
    sys.exit(1)
info = models.execute_kw(DB, uid, ADMIN_PW, 'ir.module.module', 'read', [[mids[0]], ['state']])[0]
print(f"   state={info['state']}")
if info['state'] != 'installed':
    try:
        models.execute_kw(DB, uid, ADMIN_PW, 'ir.module.module', 'button_immediate_install', [[mids[0]]])
        print("   Install triggered - wait 60s then run tests.")
    except Exception as e:
        print(f"   {e}\n   -> Install manually from Apps menu.")
else:
    print("   Already installed - ready for tests.")

print(f"\nURL: http://localhost:8069  DB: {DB}  Login: admin / {ADMIN_PW}")
