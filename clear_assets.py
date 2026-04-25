import xmlrpc.client
import sys

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

print("--- Clearing Odoo Web Assets Cache ---")
try:
    common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
    uid = common.authenticate(DB, USER, PASSWORD, {})
    if not uid:
        print("Auth failed.")
        sys.exit(1)
        
    models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
    
    # Search for all attachments that are web assets (compiled CSS/JS)
    attachment_ids = models.execute_kw(DB, uid, PASSWORD, 'ir.attachment', 'search', [[['url', '=like', '/web/assets/%']]])
    
    if attachment_ids:
        print(f"Found {len(attachment_ids)} cached asset bundles. Deleting...")
        models.execute_kw(DB, uid, PASSWORD, 'ir.attachment', 'unlink', [attachment_ids])
        print("Successfully deleted asset bundles. They will be regenerated on next load.")
    else:
        print("No cached assets found.")

    # Also clear QWeb views cache if possible, but usually deleting attachments is enough
except Exception as e:
    print(f"Error: {e}")
