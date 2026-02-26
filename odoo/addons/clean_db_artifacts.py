import logging
env.cr.execute("SELECT id, name FROM ir_ui_view WHERE arch_db::text ILIKE '%patient_name%'")
views = env.cr.fetchall()
print("Found Views with patient_name:", views)

for v_id, v_name in views:
    try:
        env['ir.ui.view'].browse(v_id).unlink()
        print(f"Deleted view {v_name} ({v_id})")
    except Exception as e:
        print(f"Error deleting view {v_id}: {e}")

env.cr.execute("SELECT id, name, model FROM ir_model_fields WHERE name = 'patient_name' AND model = 'health.alert'")
fields = env.cr.fetchall()
print("Found Ghost Fields with patient_name:", fields)

for f_id, f_name, f_model in fields:
    try:
        env.cr.execute("DELETE FROM ir_model_data WHERE model='ir.model.fields' AND res_id=%s", (f_id,))
        env.cr.execute("DELETE FROM ir_model_fields WHERE id=%s", (f_id,))
        env.cr.execute("ALTER TABLE health_alert DROP COLUMN IF EXISTS patient_name CASCADE")
        print(f"Force deleted field {f_name} from {f_model} ({f_id}) via SQL")
    except Exception as e:
        print(f"Error force deleting field {f_id}: {e}")

env.cr.commit()
print("Database cleanup complete.")
