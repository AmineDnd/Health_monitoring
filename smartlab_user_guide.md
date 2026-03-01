# SmartLab Health Monitoring - User Guide

Welcome to the SmartLab Health Monitoring System! This guide will show you how to easily use the platform for tracking patients and managing AI alerts.

---

## Section 1 — Login
1. Open your web browser and navigate to the Odoo portal (usually `http://localhost:8069`).
2. Enter your Email and Password as provided by the hospital administrator, then click **Log in**.
3. Once logged in, click the **App Launcher icon** (nine dots in the top left corner) and select **Health Monitoring**.

---

## Section 2 — Add Patient
1. Click **Patients** in the top navigation menu.
2. Click the **New** button (top left).
3. Fill in the patient's information:
   - **Name:** The patient's full name.
   - **Age & Gender:** Enter their demographic details.
   - **Assigned Doctor:** Select the physician responsible for their care.
4. The system will automatically compute the **AI Risk Level** once vitals are entered. Click the **Save** icon (cloud with a checkmark) to register the patient.

---

## Section 3 — Add Vital Signs
1. From the top navigation, click **Vitals**, or click the **Vitals** smart button directly from a patient's file.
2. Click **New** to record a new Clinical Checkup.
3. Select the **Patient**.
4. Input the metrics:
   - **Blood Pressure:** Enter Systolic (e.g., 120) and Diastolic (e.g., 80) values.
   - **Heart Rate (HR):** Beats per minute.
   - **SpO2:** Oxygen saturation percentage.
   - **Respiratory Rate:** Breaths per minute.
   - **Temperature:** Body temperature in Celsius.
   - **Glucose:** Blood sugar level in mg/dL.
5. **AI Magic:** When you click **Analyze & Save**, the SmartLab AI instantly analyzes these 6 metrics together. 
6. If the AI detects a risk, a red alert box ("Attention Required") will appear instantly with a designated **AI Risk Score**.

---

## Section 4 — Alerts
An **Anomaly** means the AI model detected vital signs that look abnormal or predict a potential health risk, even before critical human thresholds are met. When this happens, an **Alert** is automatically created.

1. Click **Alerts** in the top navigation menu.
2. You will see cards grouped by **New**, **Investigating**, and **Resolved**.
3. **To Acknowledge:** Click the blue **Acknowledge** button on a "New" card. This tells the team you are looking into it. The card moves to "Investigating".
4. **To Resolve:** Once the patient is stabilized or the alert is handled, click the green **Mark Resolved** button. 

---

## Section 5 — Dashboard
The Dashboard is your main control center.
- **KPI Cards (Top):** Shows your total patients, how many active alerts you need to check, and the number of critical emergencies pulsing in red.
- **Deep Analytics (Middle):** Click "Open Vitals Flow Chart" or "Open Alert Distribution" to see interactive graphs charting the overall health of the hospital ward over time.
- **Lists (Bottom):** Instantly see the latest AI Anomalies and Checkups as they happen in real-time.

*Thank you for using SmartLab to improve patient care!*
