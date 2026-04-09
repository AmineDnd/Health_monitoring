print("\n--- DIRECT DB QUERY ---")
env.cr.execute("""
    SELECT a.name, a.perm_read, a.perm_write, a.perm_create, g.name
    FROM ir_model_access a
    LEFT JOIN ir_model m ON a.model_id = m.id
    LEFT JOIN res_groups g ON a.group_id = g.id
    WHERE m.model = 'health.patient'
""")
for row in env.cr.fetchall():
    print(row)
print("--- END DB QUERY ---\n")
