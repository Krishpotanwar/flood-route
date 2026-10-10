# FloodRoute: YC Office Hours Review & Verification Dossier

Date: October 2026  
Status: **Complete**  
Review Artifacts:
- **Design Document:** [docs/designs/floodroute-office-hours-design.md](file:///Users/krish/Desktop/study/project/flood-route/docs/designs/floodroute-office-hours-design.md)
- **Verified Claims Dossier:** [docs/research/08-multi-source-claims-verification-dossier.md](file:///Users/krish/Desktop/study/project/flood-route/docs/research/08-multi-source-claims-verification-dossier.md)

---

## 1. YC Office Hours Diagnostic Summary

### A. The Core Strategic Wedge
FloodRoute's wedge is **not** a speculative consumer navigation app ("Waze for Floods"), nor is it a multi-year academic hydrodynamic simulation. Those paths are capital-intensive, slow to validate, and vulnerable to Google Maps.

The sharp, defensible wedge is the **Chronic Hotspot and Underpass Sentinel for Commercial Fleets and Emergency Services in Bengaluru**:
- Pre-computing physical passability across 150-300 chronic underpasses and arterial dips.
- Categorizing risk by vehicle class (`two_wheeler`, `car`, `auto_rickshaw`, `ambulance`) based on verified ground clearances (162 mm Activa, 163 mm Swift, 170 mm Bajaj RE, 200 mm Force Traveller) and Xia et al. hydrodynamic stability physics.
- Serving commercial fleet APIs (Swiggy, Zepto, Porter) to eliminate the "monsoon squeeze" (40-70% fleet dropouts during rain surges) and providing advisory dispatch feeds to 108 Emergency Ambulance operators.

### B. The 6 Forcing Questions (Executive Answers)
1. **Demand Reality:** Quick-commerce and food delivery platforms face severe operational bottlenecks during rains: order volumes spike 30-50% while 40-70% of couriers drop off to avoid drowned engines (Rs 2,500-6,000 in repairs). Platforms pay heavy rain subsidies and lose substantial GMV.
2. **Status Quo:** A broken workaround of delayed traffic police tweets (30-90 min lag), citizen WhatsApp voice notes, and coarse district-level alerts that do not integrate with navigation stacks.
3. **Desperate Specificity:** VP of Fleet Logistics / City Ops Head at quick-commerce delivery platforms in Bengaluru, and 108 Ambulance Dispatch Supervisors at EMRI Green Health Services.
4. **Narrowest Wedge:** 150-300 underpass segments in Bengaluru scored in real time (Clear/Caution/Closed) across 0-120 minute horizons, exposed via REST/GeoJSON webhooks and an automated WhatsApp bot.
5. **Observation vs Inference:** Rain gauges alone do not equal flooded streets. Static elevation dips and drainage decay curves (accounting for 45-180 minute drain-down lags) are critical to avoid clearing flooded roads prematurely.
6. **Future-Fit:** Google Flood Hub operates at a coarse 20 km x 20 km grid and cannot resolve road-segment water depths or vehicle-specific air intake limits. FloodRoute owns the local ground truth.

---

## 2. Multi-Source Verified Claims Summary

All factual, legal, economic, and physical claims across project documentation have been rigorously re-verified against independent primary sources:

- **Legal:** Bareilly bridge incident verified under Section 105 BNS (culpable homicide not amounting to murder); Geospatial Guidelines 2021 & NGP 2022 confirm Indian entity deregulation with 1m horizontal / 3m vertical foreign entity thresholds; DPDP Act 2023 mandates explicit consent for GPS tracking with penalties up to ₹250 crore; TRAI TCCCPR Third Amendment notified 18 Sep 2026.
- **Hazard Feeds:** CWC FloodWatch India 2.0 covers 592 stations and 150 reservoirs; CWC Hydro-Met Data Policy charges ₹75,000/site/year for classified data; NDMA SACHET operates active CAP 1.2 RSS feeds at `rss_india.xml`; Copernicus/ECMWF transitioned to open CC-BY 4.0 on 2 July 2025.
- **Economics:** Meta WhatsApp Business Platform confirmed at **₹0.115 per delivered utility message** (October 2026 India rate card); GeM portal charges ₹0 up to ₹10 lakh (PIB 9 August 2024 revision); DLT registration confirmed at ₹5,900 inclusive of 18% GST.
- **Physics:** Verified vehicle ground clearances and hydrodynamic floatation limits (Maruti Swift/Dzire 163 mm / 35-38 cm floating; Activa 162 mm; Ather 450X 300 mm IP67; Bajaj RE 170 mm; Force Traveller 200-210 mm).
