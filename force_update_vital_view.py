"""
force_update_vital_view.py
Directly updates the vitals form view arch in the DB via xmlrpc,
bypassing the module update system.
"""
import xmlrpc.client

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

# The corrected button line — invisible="id" restored, original method name
CORRECT_BUTTON = 'name="action_manual_save_close" class="btn-primary ms-2" invisible="id"'
WRONG_BUTTON_1 = 'name="action_check_and_save" class="btn-primary ms-2"'
WRONG_BUTTON_2 = 'name="action_manual_save_close" class="btn-primary ms-2"'  # missing invisible

common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
uid = common.authenticate(DB, USER, PASSWORD, {})
if not uid:
    print("Auth failed.")
    exit(1)

models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

# Find the view
view_ids = models.execute_kw(DB, uid, PASSWORD, 'ir.ui.view', 'search',
    [[['name', '=', 'health.vital.record.form']]])

if not view_ids:
    print("View not found! Searching by model...")
    view_ids = models.execute_kw(DB, uid, PASSWORD, 'ir.ui.view', 'search',
        [[['model', '=', 'health.vital.record'], ['type', '=', 'form']]])

print(f"Found view IDs: {view_ids}")

for vid in view_ids:
    view = models.execute_kw(DB, uid, PASSWORD, 'ir.ui.view', 'read',
        [[vid]], {'fields': ['name', 'arch_db']})[0]
    arch = view['arch_db']
    print(f"\nView: {view['name']}")

    changed = False

    # Fix 1: action_check_and_save with no invisible → restore invisible + right method
    if 'action_check_and_save' in arch:
        arch = arch.replace(
            'name="action_check_and_save" class="btn-primary ms-2"',
            'name="action_manual_save_close" class="btn-primary ms-2" invisible="id"'
        )
        # Also handle variant without invisible
        arch = arch.replace(
            'name="action_check_and_save" class="btn-primary ms-2" invisible="id"',
            'name="action_manual_save_close" class="btn-primary ms-2" invisible="id"'
        )
        changed = True
        print("  Fixed: action_check_and_save → action_manual_save_close + invisible=id")

    # Fix 2: action_manual_save_close but missing invisible
    if 'action_manual_save_close" class="btn-primary ms-2"' in arch and 'invisible="id"' not in arch.split('action_manual_save_close')[1][:80]:
        arch = arch.replace(
            'name="action_manual_save_close" class="btn-primary ms-2"',
            'name="action_manual_save_close" class="btn-primary ms-2" invisible="id"'
        )
        changed = True
        print("  Fixed: missing invisible=id on action_manual_save_close")

    # Fix 3: Remove the extreme value red banner if still present
    if 'extreme SpO' in arch or 'spo2 &gt;= 85' in arch:
        import re
        # Remove the entire extreme value banner div
        arch = re.sub(
            r'<div invisible="not id or spo2[^>]*>.*?</div>\s*</div>\s*',
            '',
            arch,
            flags=re.DOTALL
        )
        changed = True
        print("  Fixed: Removed extreme value banner")

    if changed:
        models.execute_kw(DB, uid, PASSWORD, 'ir.ui.view', 'write',
            [[vid], {'arch_db': arch}])
        print(f"  ✅ View {vid} updated in DB")
    else:
        print(f"  ℹ  View {vid} already looks correct (no changes needed)")
        # Print the button line for inspection
        for line in arch.split('\n'):
            if 'Analyze' in line or 'action_manual' in line or 'action_check' in line:
                print(f"     Button line: {line.strip()}")

print("\nDone. Now restart Odoo and hard-refresh the browser.")
