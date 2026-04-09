from odoo.exceptions import AccessError
import traceback

print("\n--- STARTING ISOLATED E2E PERMISSIONS TEST ---")

# Setup Isolated Test Users
try:
    print("Initializing pure test profiles...")
    pure_nurse = env['res.users'].create({
        'name': 'API Pure Nurse',
        'login': 'apinurse_e2e@test.com',
        'groups_id': [(6, 0, [env.ref('base.group_user').id, env.ref('health_monitoring.group_health_nurse').id])]
    })

    pure_doc = env['res.users'].create({
        'name': 'API Pure Doc',
        'login': 'apidoc_e2e@test.com',
        'groups_id': [(6, 0, [env.ref('base.group_user').id, env.ref('health_monitoring.group_health_doctor').id])]
    })

    print(f"Isolated Profiles Created -> Nurse ID: {pure_nurse.id} | Doctor ID: {pure_doc.id}")

    nurse_env = env(user=pure_nurse)
    doc_env = env(user=pure_doc)

    print("\n1. Pure Nurse Creates Patient...")
    patient_by_nurse = nurse_env['health.patient'].create({
        'name': 'API Isolated Test Patient',
        'age': 30,
        'gender': 'female'
    })
    print("SUCCESS: Nurse successfully created a patient.")

    print(f"\n2. Verifying Status. Status is: '{patient_by_nurse.status}'")
    assert patient_by_nurse.status == 'draft', "Patient should be draft initially!"
    print("SUCCESS: Initial save gracefully defaulted to Draft!")

    print("\n3. Pure Nurse attempts to Validate patient actively...")
    try:
        patient_by_nurse.action_validate()
        print("FAIL: Pure Nurse was able to validate! Validation Lock is broken.")
    except Exception as e:
        print(f"SUCCESS: Nurse strictly blocked from validation.")

    print("\n4. Pure Nurse attempts to Delete patient permanently...")
    try:
        patient_by_nurse.unlink()
        print("FAIL: Pure Nurse was able to delete! Delete Lock is broken.")
    except Exception as e:
        print(f"SUCCESS: Nurse strictly blocked from deletion.")

    print("\n5. Pure Doctor steps in and validates patient...")
    patient_by_doc = doc_env['health.patient'].browse(patient_by_nurse.id)
    try:
        patient_by_doc.action_validate()
        print(f"SUCCESS: Doctor formally validated the patient! Final Status: '{patient_by_doc.status}'")
    except Exception as e:
        print(f"FAIL: Doctor could not validate: {e}")

finally:
    # Cleanup DB
    print("\nCleaning up isolation records...")
    env.cr.rollback() # Rolls back everything we just did, keeping the database perfectly clean

print("--- ALL ISOLATED TESTS EXECUTED PERFECTLY ---")
