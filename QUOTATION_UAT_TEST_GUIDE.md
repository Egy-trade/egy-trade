# Quotation controls: Odoo 16 UAT guide

## 1. Test build and prerequisites

Run this only on a disposable Odoo 16 database restored from a recent production backup. Do not test on `live`.

Deploy the isolated branch `staging-pricing-test-20260810`, then upgrade these modules together:

```text
sale_discount_total
sale_order_product_pricing
sale_revision_history
custom_create_po_from_so
```

Example server-side test command (adapt the executable, database, and add-ons paths to the Odoo.sh build):

```bash
odoo-bin -d <DISPOSABLE_DB> --stop-after-init --test-enable \
  --test-tags /sale_discount_total,/sale_order_product_pricing,/sale_revision_history,/custom_create_po_from_so \
  -u sale_discount_total,sale_order_product_pricing,sale_revision_history,custom_create_po_from_so
```

Create separate non-admin users for: Quotation Specialist (QS), Salesperson, Quotation Manager, Sales Manager, Product Pricing User, Lighting Designer, ordinary Employee, Procurement, and Finance/Accounting Manager. Do not reuse Administrator for role tests.

Finance must configure:

- a 14% sales VAT tax;
- a negative 1% sales withholding tax with the correct withholding account and tax-report tag;
- standard payment terms and delivery terms;
- Standard Discount enabled, company maximum at or below 30%, default personal cap, and individual caps;
- the normal quotation-validity default (14 days).

## 2. Core quotation workflow

| ID | Tester | Action | Expected result |
|---|---|---|---|
| Q01 | QS | Open an existing quotation and close it without editing. | No quotation, line, audit, or preview timestamp changes. |
| Q02 | QS | Enter manual Item # values, plus section and note rows. | Exactly one Item # column exists; entered values persist; sections/notes have no generated number. |
| Q03 | Pricing User | Before any commercial edit today, click Add Below to prove the decision wizard opens. Choose Update Today, then set Global Factor, save, and click Add Below again. | One blank row is inserted below. It inherits Global Factor only; product, quantity, estimate, price, discounts, Item # are blank/default and Line Factor is 1. |
| Q04 | QS | On the first commercial edit of the Cairo day, try to save without recording a decision. | Save is rejected and directs the user to Record Commercial Change. The prominent action opens Update Today/Create Revision. No partial edit persists. |
| Q05 | QS | Choose Update Today. | Same draft remains active; Offer Date becomes Cairo today; expiry recalculates from Days of Expiry; `date_order` is unchanged; chatter/audit records user and time. |
| Q06 | QS | Choose Create Revision with a reason. | Old draft becomes inactive history; new `SXXXX-01` draft opens; copied commercial values are exact and the reason is audited. |
| Q07 | Quotation Manager, Sales Manager, and Accounting Manager | With each manager role in turn, change Days of Expiry from 14 without a reason, then with a reason. Also try as ordinary QS/Sales. | No-reason save is blocked; each manager's reasoned override succeeds with warning/audit and requires approval before issue; ordinary QS/Sales cannot override. |
| Q08 | Pricing User or Sales Manager | Click Product Pricing Preview and close it. Then open the same quotation as QS. | Preview causes no selling price, origin, offer date, audit log, or quotation-state change. QS cannot see/use Product Pricing or confidential cost controls. |
| Q09 | Authorized issuer | Click Issue Offer PDF. | Confirmation warns that a customer document will be issued. PDF is rendered once, attached to the quotation, actor/time/version are logged, state becomes Sent, and the quotation is locked. |
| Q10 | Sales/QS | Try UI edit, import, RPC write, line create/write/delete, direct state reopening, and standard Send on the issued record. | Every mutation is blocked. Normal confirmation is allowed only from the workflow-issued Sent record and cannot change commercial fields. |

Note: the daily control is a server-enforced transactional gate plus a **Record Commercial Change** wizard. Odoo's standard form Save does not itself open a custom JavaScript popup; saving without a recorded decision is rejected without persisting the edit.

## 3. Pricing, approvals, and roles

| ID | Tester | Action | Expected result |
|---|---|---|---|
| R01 | Assigned QS | As the quotation's assigned QS, assign/reassign Salesperson on an active draft; repeat by import/RPC with inactive, portal, and non-Sales users; then try on Sent. | Selector contains only active internal Sales users; backend/import/RPC rejects all invalid users; assignment changes are audited; Sent cannot be reassigned. |
| R02 | QS | Separately use the client, invoice-contact, and delivery-contact selectors, then try each selector's Create/Edit route and try deleting a contact from Contacts/direct URL. | Existing selection works; Create/Edit is absent or denied and deletion raises access denial. QS has no Purchase access. |
| R03 | Sales/QS | Apply Standard Discount to a verified Pricelist line at personal cap, then 0.01 above. Repeat draft line creation through CSV import/RPC with policy disabled and with manual/unverified origin. | At-cap save succeeds; over-cap and disabled-policy creation are blocked in UI/import/RPC. Product Pricing/manual/historical-unverified origins are ineligible. |
| R04 | Quotation Manager and Sales Manager | Set the user's personal cap below the company cap. Exceed the personal cap with no reason, then supply a reason. | No-reason save is blocked; reasoned override succeeds only within company/30% hard caps, creates protected audit evidence, clears the one-use reason, and requires issue approval. |
| R05 | Salesperson | Do not accept Sales responsibility; have issuer issue the offer. | Issue confirmation warns; issue still succeeds; exception is audited, assigned Sales/Managers are notified, and Issued Without Sales Acceptance KPI is true. |
| R06 | Assigned Salesperson | Accept responsibility, then issue a fresh draft. | Acceptance actor/time are stored and exception KPI remains false. |
| R07 | Manager, then assigned/unassigned Lighting Designers | Before release, inspect the drawing binary plus every projected free-text value (project name, internal reference, product description, drawing title, and filename) and confirm none contains prices, estimates, margins, vendors, client organization/contact, or other commercial data. Release it; test assigned access, then unassign/remove the designer and retry UI, direct URL, download, fields_get/search_read, and export. | Assigned designer sees only reviewed technical scope/drawings/products/descriptions/quantities/revision status. Unassigned/revoked designer sees no scope row or download and cannot access Sales quotation records. Structured commercial/contact fields are absent. Human content review is mandatory because the module does not sanitize free text or scan files. |
| R08 | Ordinary Employee | Open Project Directory, then try Sales quotations, Technical Quotations/Drawings, documents, direct URLs, fields_get/search_read, and export. | Only project name, internal reference, client organization, stage, owner team, and latest activity are available through the directory; lines, contacts, documents, and commercial values stay inaccessible. |
| R09 | Sales Manager | Open Product Pricing and use Certify Origin on eligible historical data, with the required evidence/reason. | Page and action are reachable for Sales Manager; backend rejects unauthorized users and the certification is audited. |
| R10 | All roles | Hover each renamed/custom field and action. | Plain-language help explains purpose, authorized user, effect, and next action for Item #, estimates/origin, pricing eligibility/warning, Preview/Apply, factors, FOC, validity, tax treatment, retention, issue, revisions, and approvals. |

## 4. Purchase Price Estimate and procurement

| ID | Tester | Action | Expected result |
|---|---|---|---|
| P01 | Pricing + Procurement | Put a non-zero Purchase Price Estimate on a service line and generate its RFQ/PO. Repeat with an MTO product. | Draft PO line starts from the stored quotation estimate converted with its saved estimate currency/rate; source quotation/line and estimate evidence are read-only. |
| P02 | Procurement | With zero estimate and a valid positive vendor pricelist, generate RFQ. | Vendor price is retained and Supplier Cost Required is false. |
| P03 | Procurement | With zero estimate and no valid vendor price, generate RFQ and confirm. | Draft line is zero with Supplier Cost Required; confirmation is blocked. Entering positive cost without reason is blocked. Cost plus reason clears the flag, records user/time, and posts an audit. |
| P04 | API user | Try to create/write PO provenance or clear Supplier Cost Required directly through import/RPC. | Protected source, estimate, and audit fields reject forgery/tampering. |

## 5. VAT, CIF, invoices, and reporting

| ID | Tester | Action | Expected result |
|---|---|---|---|
| F01 | Finance | Standard policy, base 100, no discount. | Untaxed 100; VAT +14; retention -1; total 113. Both configured taxes are on every commercial line. |
| F02 | Finance | Apply a 10% Universal Discount to base 100. | Tax base is 90; VAT 12.60; retention -0.90; total 101.70. |
| F03 | Finance | Select CIF incoterm on a new quotation. | Tax Treatment defaults to CIF - No Taxes and all line taxes are empty. Direct line-tax edits are blocked. |
| F04 | Finance | Create/post invoice from Standard quotation. | Invoice preserves treatment, retention tax reference, basis, and amount; negative withholding posts to configured account and appears with configured report tags. |
| F05 | Finance | Create/post invoice from CIF quotation. | No VAT, retention, or retention tax reference is carried. |
| F06 | Finance | Create a credit note/refund from F04. | VAT and withholding reverse to the same accounts/tags and reconciliation totals are correct. |
| F07 | Finance | Repeat F01-F06 in EGP and one foreign currency, including fractional quantities/prices. | Company/transaction currency totals, rounding, tax bases, journal entries, PDF, and portal totals agree. |
| F08 | API/Portal | Import draft values, attempt RPC bypasses, export permitted records, and view issued offer through portal. | Server controls match UI controls; confidential pricing/cost fields do not leak; portal PDF/totals equal the attached issued PDF. |

## 6. Revisions and concurrency

| ID | Tester | Action | Expected result |
|---|---|---|---|
| V01 | QS/Sales | Create revision from issued `SXXXX`, then again. | New drafts are `SXXXX-01`, `SXXXX-02`; only the active newest revision opens; original issued versions remain byte-for-byte/commercially unchanged. |
| V02 | Sales Manager | Open Revision History from newest revision. | Only its family appears, newest first; unrelated older quotations are excluded. |
| V03 | Two browser sessions | Open same current revision in both sessions and submit Create Revision nearly simultaneously. | Exactly one successor is created; the losing session receives a concurrency message and no duplicate number exists. |
| V04 | Authorized user | Restore an earlier sent family member with reason. | A new N+1 draft is created; source/current references, actor, time, reason, totals, and difference summary are audited; no existing version is overwritten. |

## 7. Release evidence and stop conditions

Capture screenshots or exports for every row above and keep the server test log. Release remains blocked if any of these is missing:

- clean module upgrade and all automated tests passing;
- non-admin role matrix proof;
- historical price-origin migration reconciliation;
- posted invoice/credit-note and tax-report reconciliation by Finance;
- Odoo.sh warning/error review;
- portal/API/import/RPC/export evidence;
- rollback rehearsal on a disposable database.

Record each case as `Pass`, `Fail`, or `Blocked`, with database/build SHA, user, timestamp, quotation number, and evidence link. Any failure requires a new build and full rerun of the affected section plus Q09-Q10, F01-F08, and V01-V04 regression gates.
