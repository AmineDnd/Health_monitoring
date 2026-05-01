import asyncio
from playwright.async_api import async_playwright
import os
import time

ARTIFACTS_DIR = r"C:\Users\amine\.gemini\antigravity\brain\ddab1d71-a120-4198-bb63-f6bf792dbffa"

async def login(page):
    await page.goto("http://localhost:8069/web/login")
    await page.fill("#login", "admin")
    await page.fill("#password", "admin")
    await page.click("button[type='submit']")
    await page.wait_for_load_state("networkidle")
    # Open Health Monitoring app
    await page.goto("http://localhost:8069/web#action=health_monitoring.action_smartlab_dashboard&model=health.patient&view_type=client")
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)

async def test_scenario_1_ghost_baseline():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        print("Logging in...")
        await login(page)
        
        # Navigate to Nurse Dashboard
        print("Navigating to Nurse Dashboard...")
        await page.click("button:has-text('Nurse Station')")
        await asyncio.sleep(2)
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "scen1_0_nurse_dashboard.png"))

        # Find the first patient and click Log Vitals
        print("Clicking Log Vitals...")
        await page.click("button.sl-log-btn >> nth=0")
        await asyncio.sleep(1)
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "scen1_1_modal_open.png"))

        # Enter ONLY Heart Rate (e.g. 75)
        print("Entering partial vitals (HR only)...")
        await page.fill("input#hr", "75")
        await page.click("button.sl-btn-primary:has-text('Save')")
        
        # Wait for modal to close and dashboard to update
        await asyncio.sleep(2)
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "scen1_2_hr_only.png"))

        # Enter ONLY SpO2
        print("Logging second vital (SpO2 only)...")
        await page.click("button.sl-log-btn >> nth=0")
        await asyncio.sleep(1)
        await page.fill("input#spo2", "98")
        await page.click("button.sl-btn-primary:has-text('Save')")
        
        await asyncio.sleep(2)
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "scen1_3_hr_and_spo2.png"))

        # Navigate to Doctor Dashboard
        print("Navigating to Doctor Dashboard...")
        await page.click("button:has-text('Triage & Analysis')")
        await asyncio.sleep(2)
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "scen2_0_doctor_dashboard.png"))

        # Navigate to Admin Dashboard
        print("Navigating to Admin Dashboard...")
        await page.click("button:has-text('Hospital Operations')")
        await asyncio.sleep(3)
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "scen3_0_admin_dashboard.png"))
        
        await browser.close()
        print("Tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_scenario_1_ghost_baseline())
