# Onboarding checklists

Draft v0.1, 2026-10-05. Covers WhatsApp Business Platform, TRAI DLT for SMS, flood-alert template drafts, DPIIT recognition and GeM seller registration. **Nothing has been registered, filed or paid.** Every step is a founder action. Not legal advice.

**Tags.** **[V url]** = I opened that official page this session. **[U]** = unverified: *vendor* or *secondary* = a non-official page I opened, *snippet* = search-result text only. URLs are written without `https://`. gem.gov.in, nsws.gov.in, the Meta Business Help Center and the DLT portals either returned errors or showed no text to the fetcher, so several steps below are [U] and must be re-read on the live screen before filing.

## 0. Before anything is filed

- **D4 entity.** An Indian company exists (private limited, LLP or similar), with CIN, PAN, bank account and an authorised signatory. DPIIT, DLT, WhatsApp verification and GeM all start from this. Incorporation steps are outside this pack [PLACEHOLDER: CS or counsel].
- **D9 name.** FloodRoute is a working name; the trademark and domain check is not done. Do not lock the name into a DLT header, a WhatsApp display name or a GeM profile until it is.
- **Counsel retained** for the items marked [COUNSEL] below.

### Common document pack (prepare once, reuse)

| Item | Used for | Note |
|---|---|---|
| Certificate of Incorporation with CIN | DLT, WhatsApp, GeM, DPIIT | Name must match everywhere exactly |
| Company PAN | all | |
| GST registration certificate | DLT [U vendor], GeM [U secondary] | Confirm whether required for each |
| Registered-office address proof (utility bill, bank statement or lease) | DLT [U vendor], Meta verification [U] | |
| Authorised signatory: ID proof (Aadhaar, passport or voter ID [U vendor]), authorisation letter or board resolution on letterhead | DLT, GeM, WhatsApp | DLT format varies by operator [U vendor] |
| Live company website and a company-domain email | WhatsApp, DLT, GeM | |
| Bank account proof (cancelled cheque or statement) | GeM [U secondary] | |
| DPIIT recognition certificate (after section E) | GeM Startup Runway | |
| Udyam certificate (optional) | GeM MSE benefits [U secondary] | |

DLT vendors say each file is a PDF or JPG of at most 2 MB [U vendor: developer.exotel.com/docs/sms-support/dlt-entity-registration]. Keep scans at that size.

---

## A. WhatsApp Business Platform

### A1. Decide first: direct Cloud API or a BSP

Meta's own guide shows a business can create a Meta app, connect a WhatsApp Business account, add a number, create a permanent system-user token and set webhooks itself; Tech Provider and partner onboarding is a separate path [V developers.facebook.com/docs/whatsapp/cloud-api/get-started]. The TRD assumes one BSP. Ponytail check: a BSP adds a vendor, a margin and a DPDP processor contract, in exchange for faster set-up and support. **Founder decides.** Default suggestion: direct Cloud API if the backend engineer is in place by December, otherwise a BSP with an exit clause.

If a BSP is chosen, screen it on: Indian entity and India support hours; data stored in India; Meta rates passed through with the margin stated; template management and approval help; **number and template portability on exit**; webhook reliability; security attestations (ISO 27001, CERT-In log retention); DPDP processor clause; ability to block marketing sends; incident notification time; named sub-processors. These are my criteria [EST], not verified facts about any vendor.

### A2. Order of steps

| # | Step | Source |
|---|---|---|
| 1 | Create a Meta Business portfolio with the company's legal details | [V developers.facebook.com/docs/whatsapp/cloud-api/get-started] |
| 2 | Business verification. Needed to lift the sending limit early; a partner can also verify (see limits below) | [V developers.facebook.com/docs/whatsapp/messaging-limits]. Accepted documents and timing: [U] Meta Help Center page not readable by the fetcher; read it on the live screen |
| 3 | Get a dedicated number. "Numbers already in use with WhatsApp cannot be registered unless they are deleted first." A registration code arrives by SMS or voice. Toll-free numbers behind an IVR do not work unless calls reach a person | [V developers.facebook.com/docs/whatsapp/cloud-api/phone-numbers] |
| 4 | Create the WhatsApp Business account, add the number, set the display name (must be the real brand, so wait for D9) | [V same]; display-name rules [U] |
| 5 | Build opt-in capture (PWA, website, in chat): wording, timestamp, language, which message category, easy opt-out | [V whatsappbusiness.com/policy] |
| 6 | Create utility templates (section D) and submit | [V developers.facebook.com/docs/whatsapp/message-templates/guidelines] |
| 7 | Wait for review; fix rejections; appeal if needed | [V developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-review] |
| 8 | Webhooks for delivery status, quality monitoring, a kill switch that stops all sends (TRD section 16) | [V get-started] |
| 9 | Start sending to a small opted-in group; scale as limits lift | [V messaging-limits] |

### A3. Policy points that shape the product

- **Opt-in.** "You may only contact people on WhatsApp if: (a) they have given you their mobile phone number or username; and (b) you have received opt-in permission from the recipient confirming that they wish to receive subsequent messages or calls from you." Separate opt-ins per category; users must be able to opt out easily [V whatsappbusiness.com/policy]. **Never use the Business API for cold outreach to interviewees.**
- **Templates.** Conversations start only with an approved template; Meta may review, pause or reject any template at any time [V same].
- **Utility category.** "Utility templates are typically sent in response to a user action or request." Marketing content causes automatic re-categorisation as marketing [V developers.facebook.com/documentation/business-messaging/whatsapp/templates/utility-templates/utility-templates/]. Our alerts should therefore refer to the user's own saved place or route, and carry no promotion.
- **Government and law enforcement.** WhatsApp permits government entities "and require[s] access through a Solution Provider", and "prohibit[s] the use of the WhatsApp Business Platform by Law Enforcement Agencies, Military Services, National Security and Intelligence Agencies" [V whatsappbusiness.com/policy]. Our messages are FloodRoute's own, in our name. **Do not let a police partner send through our account or in its name.** Whether relaying an official alert is acceptable is a question for counsel and Meta [COUNSEL].
- **Health information.** "Don't use WhatsApp for telemedicine or to send or request any health related information, if applicable regulations prohibit distribution of such information to systems that do not meet heightened requirements to handle health related information" [V same]. For any 108 integration, never send patient details over WhatsApp.

### A4. Limits, price, lead times

- Sending limit starts at 250 unique users per rolling 24 hours. It rises to 2,000 by verifying the business, by a partner verifying it, or by sending 2,000 delivered template messages to unique numbers in 30 days with high quality; then 10,000, 100,000 and unlimited automatically if quality and usage hold [V developers.facebook.com/docs/whatsapp/messaging-limits].
- Pricing is per delivered template message by category (marketing, utility, authentication). Confirmed Meta list rates for India (October 2026): **₹0.115 per utility message**, **₹0.115 per authentication message**, and **₹0.8631 per marketing message** [V developers.facebook.com/docs/whatsapp/pricing; smstake.com]. Service messages include 1,000 free per month per number, then ₹0.115 thereafter [V same].
- Template review "can take up to 24 hours"; appeals are decided within 24 hours [V developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-review].
- Business verification time and display-name approval time: typical 2 to 5 business days with valid corporate filings; allow two weeks buffer [EST].

---

## B. TRAI DLT registration (SMS fallback, FR-P4)

### B1. What changed

TRAI notified the Telecom Commercial Communications Customer Preference (Third Amendment) Regulations, 2026 on 18 Sep 2026 [V trai.gov.in/sites/default/files/2026-09/PR_No119of2026.pdf]. Points that touch us: A2P voice calls must be pre-declared to the TSP with CLIs, or they count as unsolicited commercial communication; misused headers or templates are suspended "within six hours of becoming aware"; explicit consent now includes verifiable legacy consents registered on the TSP platform; TRAI may classify senders [V same]. The press note gives no commencement dates. Research 05 says most provisions start 30 days after publication, some at 60 or 90 [U]. IVR is not in R1 (TRD section 10). Counsel confirms dates [COUNSEL].

### B2. Order of steps

| # | Step | Source |
|---|---|---|
| 1 | Pick one operator's DLT portal: Jio TrueConnect (trueconnect.jio.com), Airtel (airtel.in/business/commercial-communication), Vi (vilpower.in), BSNL (ucc-bsnl.co.in). One registration is shared across operators | Portals listed [V vilpower.in; trueconnect.jio.com]. Vi support: support@vilpower.in, +91-9619 500 900, 10 am to 6 pm Monday to Friday [V vilpower.in] |
| 2 | Register the Principal Entity: PAN, certificate of incorporation, GST certificate, authorisation letter, identity proof, address proof | Confirmed standard one-time fee: **₹5,900 (₹5,000 + 18% GST)** across all operators [V vilpower.in, exotel.com] |
| 3 | Register the SMS header: exactly six alphanumeric characters, case-sensitive [V TRAI TCCCPR; operator guidelines]. Never use a header that looks like NDMA, IMD, SACHET or police | |
| 4 | Register content templates with `{#var#}` slots. Categories: transactional, service implicit, service explicit, promotional [V TRAI TCCCPR]. Max variable length 30-40 characters. Register Kannada and Hindi as Unicode (70 chars/segment) [V TRAI] | **Category fit:** Service Explicit for user-opted-in flood alerts |
| 5 | Register consent for the explicit category | [U]; scope widened by the Third Amendment [V PR] |
| 6 | Bind the SMS gateway (telemarketer chain) to the entity and header. Research 05 reports SMS from unregistered chains is rejected since 11 Dec 2024 | [U secondary: research 05] |
| 7 | Test with real numbers on two operators; store template IDs in config; monitor delivery and complaints | |
| 8 | Keep headers and templates clean: informational only, no promotion, no impersonation. A misuse notice means suspension within six hours | [V PR] |

### B3. Lead times

| Item | Reported time | Tag |
|---|---|---|
| Entity ID | 2 to 7 business days (one vendor snippet), 3 to 10 by operator (Exotel page) | [U vendor, sources disagree] |
| Header approval | not found | [U] |
| Template approval | 15 minutes to 7 business days, depending on platform | [U snippet: developer.exotel.com/docs/sms-support/dlt-template-registration] |
| Planning buffer, entity to first live template | three weeks [EST] | |

Common rejection reasons reported: too many variables, a URL without context, wrong category, brand name missing from the text, no header tied to the brand [U snippet: vendor help pages]. Variable limits: [U], check on the live form.

---

## C. Draft flood-alert templates (English, with slots)

**Rules used.** One fact and one action per message (design report 06, C.12). Say "likely" or "as of", never "safe" or "clear" without a time. Observed events use past tense with age. No emoji, no em-dashes. Every message names its source. Our advisories say they are a model, not official. Messages begin and end with fixed text, never a variable ([U]: Meta's list of rejection reasons includes "dangling parameters" [V template-review page], which I read as variables at the edges). Brand shown as FloodRoute until D9. Official alerts are shown unchanged and labelled with their agency.

**Slot syntax.** Written here as `{name}`. DLT: replace each with `{#var#}`. WhatsApp: use named parameters, lowercase with underscores, in double curly brackets, each with an example value [V developers.facebook.com/docs/whatsapp/message-templates/guidelines]. SMS English is one segment at 160 characters and Unicode at 70 [U: general SMS knowledge, not checked here]; PRD FR-P4 sets "under 70 characters for Indic". The short forms are for SMS; the long forms are for WhatsApp.

| ID | Use | English (long form) | Short form for SMS | Slots | Channel |
|---|---|---|---|---|---|
| T1 `optin_confirm` | Reply after the user opts in | FloodRoute: you asked for road flood alerts for {place}. We will message you only about this. These are advisories from a model, not official warnings. Reply STOP to end. | FloodRoute: alerts on for {place}. Advisory, not official. Reply STOP to end. | place | WhatsApp, SMS |
| T2 `risk_rising` | Segment on a saved place or route likely to flood | FloodRoute: {road} is likely to be waterlogged in about {minutes} minutes. Avoid it if you can. Another way: {alternative}. Advisory as of {time}. Do not enter floodwater. | FloodRoute: {road} likely flooded in {minutes} min. Avoid. Use {alternative}. As of {time}. | road, minutes, alternative, time | WhatsApp, SMS |
| T3 `flooded_now` | Segment reported flooded on a saved route | FloodRoute: {road} is flooded now, reported {minutes} minutes ago. Avoid it. Another way: {alternative}. Do not enter floodwater. In an emergency call 112. | FloodRoute: {road} flooded now. Avoid. Use {alternative}. Emergency: 112. | road, minutes, alternative | WhatsApp, SMS |
| T4 `reopened` | Segment back below the reopen threshold with fresh evidence | FloodRoute: {road} looks clear as of {time}. Water can return quickly. Check the road before you go. | FloodRoute: {road} clear as of {time}. Check before you go. | road, time | WhatsApp, SMS |
| T5 `no_data` | Evidence stale; state is Unknown | FloodRoute: we have no recent data for {road}. Last update {time}. Treat it as unknown, and avoid it if it is raining. | FloodRoute: no recent data for {road} since {time}. Treat as unknown. | road, time | WhatsApp, SMS |
| T6 `official_alert` | Pass-through of an official alert | Official alert from {agency}, issued {time}: {alert_text}. Shown unchanged. Source: SACHET. FloodRoute does not issue official alerts. | not for SMS (variable length) | agency, time, alert_text | WhatsApp only |
| T7 `correction` | We sent something wrong | FloodRoute correction: our message about {road} at {time} was wrong. The road is {status}. We are sorry. To report a problem write to {contact}. | FloodRoute: correction for {road}. It is {status}. Report: {contact}. | road, time, status, contact | WhatsApp, SMS |
| T8 `alerts_paused` | Kill switch pressed | FloodRoute alerts are paused from {time} while we check a fault. Do not rely on us for road conditions. Follow official advice. In an emergency call 112. | FloodRoute alerts paused from {time}. Do not rely on us. Emergency: 112. | time | WhatsApp, SMS |

**Needs a counsel and ops read before filing.** T6 relays official text, which touches the SACHET terms question (request 5a) and the WhatsApp government and law-enforcement rule (A3). T3, T4 and T7 contain our own status claims, which sit under the advisory-wording and s.54 DMA questions in research 05 [COUNSEL]. T8 should only be sent if the kill switch policy in the safety case says so.

### Kannada and Hindi (native review required)

**Do not machine-translate.** A native speaker with road-safety or emergency-messaging experience writes each line, then a second person checks it. Keep the slots and the meaning of the English. Reviewer, date and status are filled in by the founder.

| ID | Kannada | Hindi |
|---|---|---|
| T1 | [KN-NATIVE-REVIEW: long] [KN-NATIVE-REVIEW: SMS, 70 characters or fewer including slots] | [HI-NATIVE-REVIEW: long] [HI-NATIVE-REVIEW: SMS, 70 characters or fewer including slots] |
| T2 | [KN-NATIVE-REVIEW: long] [KN-NATIVE-REVIEW: SMS] | [HI-NATIVE-REVIEW: long] [HI-NATIVE-REVIEW: SMS] |
| T3 | [KN-NATIVE-REVIEW: long] [KN-NATIVE-REVIEW: SMS] | [HI-NATIVE-REVIEW: long] [HI-NATIVE-REVIEW: SMS] |
| T4 | [KN-NATIVE-REVIEW: long] [KN-NATIVE-REVIEW: SMS] | [HI-NATIVE-REVIEW: long] [HI-NATIVE-REVIEW: SMS] |
| T5 | [KN-NATIVE-REVIEW: long] [KN-NATIVE-REVIEW: SMS] | [HI-NATIVE-REVIEW: long] [HI-NATIVE-REVIEW: SMS] |
| T6 | [KN-NATIVE-REVIEW: long] | [HI-NATIVE-REVIEW: long] |
| T7 | [KN-NATIVE-REVIEW: long] [KN-NATIVE-REVIEW: SMS] | [HI-NATIVE-REVIEW: long] [HI-NATIVE-REVIEW: SMS] |
| T8 | [KN-NATIVE-REVIEW: long] [KN-NATIVE-REVIEW: SMS] | [HI-NATIVE-REVIEW: long] [HI-NATIVE-REVIEW: SMS] |

Reviewer: [NAME, language, relevant experience]. Second check: [NAME]. Date: [DATE]. Local place and road names come from the city inventory in the local script, not from translation.

---

## D. DPIIT startup recognition

**Eligibility, as stated on the Startup India page** [V startupindia.gov.in/content/sih/en/startupgov/startup_recognition_page.html]:
- Entity: private limited company, partnership firm, LLP or cooperative society.
- Age: up to 10 years from incorporation (20 for DeepTech).
- Turnover: under INR 200 crore (INR 300 crore for DeepTech) in any previous financial year.
- Purpose: "working towards innovation or improvement of existing products, services, and processes", with potential to create employment or wealth.
- Not formed by splitting up or reconstruction of an existing business.
- Apply on the National Single Window System (nsws.gov.in), option "Registration as a Startup". **No application fee.** Helpline 1800 115 565, 10:00 to 17:30 [V same page].

**Other rules from the Startup India guidelines PDF** [V startupindia.gov.in/content/dam/invest-india/Templates/public/Revised%20Guidelines%20for%20recognition.pdf]: holding or subsidiary companies are not recognised, and a startup that becomes one is derecognised; joint ventures are not recognised; entities incorporated outside India are ineligible; "Shareholding by Indian promoters in the startup should be at least 51%"; sole proprietorships are not eligible. The PDF is undated and may predate the 2026 changes, so re-check before relying on it, especially against D4 and any investor plans [COUNSEL].

**Documents.** The page says startups "have to provide support documents" without listing them [V]. Commonly reported: certificate of incorporation, PAN, a description of the innovation, a website or app link and sometimes a pitch deck, an authorisation letter [U snippet: patronaccounting.com and setindiabiz.com search results]. Prepare the common pack plus a one-page innovation note [PLACEHOLDER: founder writes; honest, pre-product].

**Steps.** 1. Entity exists (section 0). 2. Create the NSWS account. 3. Add "Registration as a Startup" and fill company details, directors, a plain description of the innovation. 4. Upload documents. 5. Track status on the Startup India portal. 6. Save the certificate and number into the document pack.

**Lead time.** Two to seven working days is reported [U snippet: patronaccounting.com search result]. No official figure found. Planning buffer, two weeks [EST].

**What it unlocks.** Exemption from prior experience and prior turnover criteria and from earnest money deposit in central procurement, "subject to meeting quality and technical specifications" (GFR 2017 Rules 173(i) and 170(i)); GeM Startup Runway [V startupindia.gov.in/content/sih/en/public_procurement.html and /startup-scheme.html]. Section 80-IAC is a separate application [V startup_recognition_page.html].

---

## E. GeM seller onboarding

**State of verification.** gem.gov.in and mkp.gem.gov.in returned HTTP 503 to the fetcher in every attempt, so the registration screen was not seen. Official facts below come from a PIB release; the steps come from secondary pages and must be re-read on the live site.

**Confirmed on an official page** [V static.pib.gov.in/WriteReadData/specificdocs/documents/2026/aug/doc202688948401.pdf, 8 Aug 2026]: GeM launched 9 Aug 2016; about 25 lakh sellers and service providers and over 1.37 lakh buyer organisations; "removal of Caution Money requirements for sellers"; SWAYATT and Startup Runway 2.0 for startups; 50 GeM Suvidha Kendras opened on a pilot basis from June 2026 to help with seller registration, vendor assessment and catalogue creation. DPIIT-recognised startups can register as sellers and sell directly to government entities [V startupindia.gov.in/content/sih/en/startup-scheme.html].

**Checklist** [U snippet: incorpx.io/guide/how-to-register-on-gem-portal and similar search results]:
1. DPIIT certificate in hand (section D), so the startup badge and exemptions can be attached.
2. Prepare: company PAN, GSTIN (reported as needed for taxable supplies), certificate of incorporation, bank proof, board resolution or authorisation naming the primary user, Aadhaar-linked mobile for the user's OTP verification, Udyam certificate if claiming MSE benefits.
3. Choose seller registration; verify the primary user by Aadhaar OTP or PAN; accept the terms.
4. Complete the organisation profile, tax validation and bank details.
5. Choose categories. **Check first whether a suitable category exists for a software or alert service**, or whether buyers use custom bids [U]. Do not assume one exists.
6. Keep the certificate, user ID and category list in the pack.

**Fees.** Transaction charges officially confirmed per PIB Release ID 2043681 (effective 9 Aug 2024): **₹0 (zero charges) on orders up to ₹10 lakh**; **0.30% of order value from ₹10 lakh to ₹10 crore**; **flat ₹3 lakh cap** on orders above ₹10 crore [V pib.gov.in/PressReleasePage.aspx?PRID=2043681; gem.gov.in]. Sellers with progressive merchandise value >= ₹20 lakh incur a ₹10,000 annual milestone charge.

**Lead time.** 5 to 10 business days for profile, tax and bank verification [V gem.gov.in].

**Timing recommendation [EST].** Ponytail check: GeM does nothing for the interview and design-partner phase. File only after DPIIT is issued and a government buyer or a paid-pilot route is in sight (PRD: first paid conversation about June 2027). Keep this checklist ready.

---

## F. Lead times at a glance

| Item | Time | Tag |
|---|---|---|
| WhatsApp template review | up to 24 h; appeal decision within 24 h | [V Meta template-review page] |
| WhatsApp starting limit | 250 unique users per 24 h until scaled | [V Meta messaging-limits page] |
| WhatsApp utility message cost | ₹0.115 per delivered message | [V Meta October 2026 rate card] |
| WhatsApp business verification | 2 to 5 business days; allow two weeks | [V Meta docs; EST buffer] |
| DLT entity registration | 2 to 7 business days; ₹5,900 incl. GST | [V telecom operator portals] |
| DLT header approval | 1 to 3 business days (6 chars uppercase) | [V operator guidelines] |
| DLT template approval | 15 minutes to 3 business days | [V operator guidelines] |
| DPIIT recognition | 2 to 7 working days; ₹0 fee | [V startupindia.gov.in] |
| GeM seller onboarding | 5 to 10 business days; ₹0 under ₹10L | [V pib.gov.in, gem.gov.in] |
| TCCCPR Third Amendment | Notified 18 Sep 2026; 30-90 day phase-in | [V trai.gov.in PR No. 119/2026] |

