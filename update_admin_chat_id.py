admin = env['res.users'].search([('login', 'in', ['admin', 'admin@example.com'])], limit=1)
if admin:
    admin.write({'telegram_chat_id': '7100068465'})
    env.cr.commit()
    print(f"Successfully updated telegram_chat_id for {admin.name} to {admin.telegram_chat_id}")
else:
    print("Could not find admin user.")
