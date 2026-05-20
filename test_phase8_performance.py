"""Phase 8 read-only dashboard and query performance smoke tests.

The script intentionally does not create, modify, or delete clinical data.
It checks that optimized dashboard RPCs remain consistent with backend counts
and finish within conservative local-development thresholds.
"""
import os
import sys
import time
import xmlrpc.client


URL = os.environ.get("ODOO_URL", "http://localhost:8069")
DB = os.environ.get("ODOO_DB", "smartlab_db")
ADMIN_USER = os.environ.get("ODOO_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ODOO_PASSWORD", "admin")


def fail(message):
    print(f"[FAIL] {message}")
    sys.exit(1)


def authenticate(username=ADMIN_USER, password=ADMIN_PASSWORD):
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, username, password, {})
    if not uid:
        fail(f"Could not authenticate {username!r} against {DB!r}")
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")
    return uid, password, models


def call(models, uid, password, model, method, args=None, kwargs=None):
    return models.execute_kw(DB, uid, password, model, method, args or [], kwargs or {})


def timed(label, fn, max_seconds):
    started = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - started
    print(f"[OK] {label}: {elapsed:.3f}s")
    if elapsed > max_seconds:
        fail(f"{label} took {elapsed:.3f}s; expected <= {max_seconds:.3f}s")
    return result


def assert_equal(label, actual, expected):
    if actual != expected:
        fail(f"{label}: got {actual!r}, expected {expected!r}")
    print(f"[OK] {label}: {actual!r}")


def main():
    uid, password, models = authenticate()

    active_domain = [["admission_status", "in", ["triage", "admitted"]]]
    open_alert_domain = [["state", "!=", "resolved"], ["status", "!=", "handled"]]
    critical_domain = open_alert_domain + [["severity", "=", "critical"]]

    nurse = timed(
        "nurse dashboard RPC",
        lambda: call(models, uid, password, "health.dashboard", "get_nurse_dashboard_data"),
        4.0,
    )
    active_count = call(models, uid, password, "health.patient", "search_count", [active_domain])
    assert_equal("nurse active patient KPI", nurse["stats"]["total"], active_count)

    admin = timed(
        "admin dashboard RPC",
        lambda: call(models, uid, password, "health.dashboard", "get_admin_dashboard_data", ["week"]),
        3.0,
    )
    critical_count = call(models, uid, password, "health.alert", "search_count", [critical_domain])
    assert_equal("admin active critical KPI", admin["kpi"]["criticalAlerts"], critical_count)

    analytics = timed(
        "analytics dashboard RPC",
        lambda: call(models, uid, password, "health.dashboard", "get_analytics_dashboard_data", ["90"]),
        3.0,
    )
    if len(analytics["vitalsPerDay"]) != 90 or len(analytics["avgScorePerDay"]) != 90:
        fail("analytics 90-day charts did not return exactly 90 buckets")
    print("[OK] analytics chart buckets: 90 days")

    # A small repeated-read loop catches accidental N+1 regressions without
    # generating load or touching production data.
    timed(
        "repeated dashboard reads",
        lambda: [
            call(models, uid, password, "health.dashboard", "get_admin_dashboard_data", ["week"])
            for _ in range(3)
        ],
        6.0,
    )

    print("\nPHASE 8 PERFORMANCE SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
