from datetime import timedelta
from odoo import fields

print("\n--- STARTING ESCALATION TEST ---\n")

# Find a test alert
alert = env['health.alert'].search([], limit=1)
if not alert:
    print("No health alert found to test. Test aborted.")
else:
    # Reset alert
    alert.write({
        'status': 'pending', 
        'escalation_level': 0,
        'created_at': fields.Datetime.now()
    })
    env.cr.commit()
    print("1. Alert reset to pending at level 0.")
    
    # 1. Emulate 6 minutes passing
    alert.write({'created_at': fields.Datetime.now() - timedelta(minutes=6)})
    env['health.alert']._cron_escalate_alerts()
    env.cr.commit()
    print(f"2. After 6 mins -> Escalation Level: {alert.escalation_level} (Expected: 1)")
    
    # 2. Emulate 16 minutes passing
    alert.write({'created_at': fields.Datetime.now() - timedelta(minutes=16)})
    env['health.alert']._cron_escalate_alerts()
    env.cr.commit()
    print(f"3. After 16 mins -> Escalation Level: {alert.escalation_level} (Expected: 2)")

    # 3. Emulate 31 minutes passing
    alert.write({'created_at': fields.Datetime.now() - timedelta(minutes=31)})
    env['health.alert']._cron_escalate_alerts()
    env.cr.commit()
    print(f"4. After 31 mins -> Escalation Level: {alert.escalation_level} (Expected: 3)")
    print(f"   Final Status: {alert.status} (Expected: escalated)")
    
    print("\n--- TEST COMPLETED ---")
