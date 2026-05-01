import sys
sys.path.insert(0, '/usr/lib/python3/dist-packages')
sys.path.insert(0, '/usr/lib/python3.10')

import odoo
from odoo.api import Environment
from odoo import SUPERUSER_ID

# Init odoo
odoo.tools.config.parse_config(['--config=/etc/odoo/odoo.conf'])
db = 'smartlab_db'

registry = odoo.registry(db)
with registry.cursor() as cr:
    env = Environment(cr, SUPERUSER_ID, {})
    # Check ir.asset records for health_monitoring
    assets = env['ir.asset'].search([('bundle', '=', 'web.assets_backend')])
    health_assets = [(a.path, a.bundle) for a in assets if 'health' in (a.path or '')]
    print("Health monitoring assets in ir.asset:")
    for path, bundle in health_assets:
        print(f"  {path}")
    
    if not health_assets:
        print("NO health_monitoring assets found in ir.asset!")
        # Check total count
        total = len(assets)
        print(f"Total web.assets_backend entries: {total}")
        # Show some examples
        for a in assets[:5]:
            print(f"  example: {a.path}")
