# SmartLab Architecture & PFE Presentation Explanation

## What UI Improvements Were Applied?

1. **Modern Color Palette:** We replaced default Odoo colors with standard medical SaaS colors: Soft Medical Blue (`#3A86FF`) for primary actions, Amber (`#F59E0B`) for warnings, and Soft Red (`#EF4444`) for critical emergencies. 
2. **Typography & Hierarchy:** We introduced modern fonts (`Inter` for reading comfort, `JetBrains Mono` for precise medical metrics) and increased padding and spacing to let the interface "breathe".
3. **SaaS Dashboard Rebuild:** Instead of a generic list, the dashboard is now a centralized command center. It features card-based KPIs with soft shadows, dedicated visual layout blocks for analytics, and embedded real-time lists.
4. **Component Grouping:** The Vital forms were restructured from single-value logs into cohesive "Clinical Checkups" with designated Cardiovascular and Metabolic sections.

## Why Do They Improve Usability?
- **Reduced Cognitive Load:** Healthcare professionals work long, stressful shifts. A clean, spacious, low-contrast interface (using soft grays and muted whites) prevents eye strain compared to harsh, busy layouts.
- **Visual Urgency:** By reserving the color Red strictly for critical cards—and adding a subtle CSS pulsing animation—nurses immediately know where their attention is required without reading text.
- **Fewer Clicks:** Grouping all 6 vital signs into a single clinical checkup form saves time compared to entering them one by one. Similarly, placing deep link buttons ("Interactive Analytics") directly on the dashboard speeds up navigation.

## How Does This Make the System Professional?
A professional, production-ready system must instill trust. When an interface looks like a cohesive product—with purposeful hover animations, rounded corners (12px radius), badge pills, and clean borders—it signals to the jury that this isn't just a backend script hacked into Odoo. It is a thoughtfully designed SaaS product built for humans.

---

## System Architecture Overview (For the Jury)

**1. The Foundation (Odoo 17)**
Odoo acts as the core database and user interface. It handles security (Nurse vs. Doctor permissions), historical data storage, and the kanban workflows.

**2. The AI Engine (FastAPI + Machine Learning)**
We decoupled the heavy AI computation from Odoo. Odoo makes an HTTP POST request to a FastAPI microservice. The microservice uses an Isolation Forest (Machine Learning) model.

**3. The Workflow (How it connects)**
1. A nurse enters 6 vital signs in Odoo and clicks Save.
2. Odoo instantly sends a JSON payload of these 6 vitals to FastAPI.
3. The AI scores the vitals in milliseconds and sends back an anomaly probability (e.g., 82% risk) and a severity ruling.
4. Odoo receives this, updates the UI to show a red "Attention Required" box, and automatically triggers an Alert in the Kanban pipeline for Doctors to investigate.
