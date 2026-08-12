# Quotation controls: Odoo 16 UAT guide

## 1. Test build and prerequisites

Run this only on a disposable Odoo 16 database restored from a recent production backup. Do not test on `live`.

Deploy the final approved commit from `codex/quotation-uat-completion` to the
isolated Odoo.sh branch `staging-pricing-test-20260810`. Test only the Odoo.sh
build whose SHA exactly matches that final commit (it must contain `7202e97`
and the follow-up R03 origin-integrity fix). Record the deployed SHA with the
evidence; do not test an older branch or build. Then upgrade these modules
together:

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

Before testing, Accounting must verify the existing configuration (do not create
or change taxes, accounts, tax tags, or tax repartition rules during this UAT):

- a 14% sales VAT tax;
- the existing 1% sales withholding tax, including its rate, account and report tag;
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
| R03 | Sales/QS | Apply Standard Discount to a verified Pricelist line at personal cap, then 0.01 above. Repeat draft line creation through CSV import/RPC with policy disabled and with manual/unverified origin. Also try changing Selling Price and Standard Discount together in one UI save/import/RPC write. | At-cap save succeeds; over-cap and disabled-policy creation are blocked in UI/import/RPC. Product Pricing/manual/historical-unverified origins are ineligible. A combined manual-price/Standard-Discount write is rejected without changing either value, including for management. |
| R04 | Quotation Manager and Sales Manager | Set the user's personal cap below the company cap. Exceed the personal cap with no reason, then supply a reason. | No-reason save is blocked; reasoned override succeeds only within company/30% hard caps, creates protected audit evidence, clears the one-use reason, and requires issue approval. |
| R05 | Salesperson | Do not accept Sales responsibility; have issuer issue the offer. | Issue confirmation warns; issue still succeeds; exception is audited, assigned Sales/Managers are notified, and Issued Without Sales Acceptance KPI is true. |
| R06 | Assigned Salesperson | Accept responsibility, then issue a fresh draft. | Acceptance actor/time are stored and exception KPI remains false. |
| R07 | Manager, then assigned/unassigned Lighting Designers | Before release, inspect the drawing binary plus every projected free-text value (project name, internal reference, product description, drawing title, and filename) and confirm none contains prices, estimates, margins, vendors, client organization/contact, or other commercial data. Release it; test assigned access, then unassign/remove the designer and retry UI, direct URL, download, fields_get/search_read, and export. | Assigned designer sees only reviewed technical scope/drawings/products/descriptions/quantities/revision status. Unassigned/revoked designer sees no scope row or download and cannot access Sales quotation records. Structured commercial/contact fields are absent. Human content review is mandatory because the module does not sanitize free text or scan files. |
| R08 | Ordinary Employee | Open Project Directory, then try Sales quotations, Technical Quotations/Drawings, documents, direct URLs, fields_get/search_read, and export. | Only project name, internal reference, client organization, stage, owner team, and latest activity are available through the directory; lines, contacts, documents, and commercial values stay inaccessible. |
| R09 | Sales Manager | On an active draft/revision with a Historical-Unverified line, open Product Pricing and use Certify Origin with the required evidence/reason; repeat against an immutable Sent version. | Draft/revision certification records the verified origin and audit without changing the selling price; unauthorized users and Sent-version certification are rejected, and the Sent version remains unchanged. |
| R10 | All roles | Hover each renamed/custom field and action. | Plain-language help explains purpose, authorized user, effect, and next action for Item #, estimates/origin, pricing eligibility/warning, Preview/Apply, factors, FOC, validity, VAT, withholding, issue, revisions, and approvals. |

## 4. Purchase Price Estimate and procurement

| ID | Tester | Action | Expected result |
|---|---|---|---|
| P01 | Pricing + Procurement | Put a non-zero Purchase Price Estimate on a service line and generate its RFQ/PO. Repeat with an MTO product. | Draft PO line starts from the stored quotation estimate converted with its saved estimate currency/rate; source quotation/line and estimate evidence are read-only. |
| P02 | Procurement | With zero estimate and a valid positive vendor pricelist, generate RFQ. | Vendor price is retained and Supplier Cost Required is false. |
| P03 | Procurement | With zero estimate and no valid vendor price, generate RFQ and confirm. | Draft line is zero with Supplier Cost Required; confirmation is blocked. Entering positive cost without reason is blocked. Cost plus reason clears the flag, records user/time, and posts an audit. |
| P04 | API user | Try to create/write PO provenance or clear Supplier Cost Required directly through import/RPC. | Protected source, estimate, and audit fields reject forgery/tampering. |

## 5. Global VAT, withholding, confirmation, and invoices

| ID | Tester | Action | Expected result |
|---|---|---|---|
| T01 | QS | Create a new quotation. | **VAT 14%** is selected; **1% Withholding** is clear. Odoo's existing VAT tax is proposed on every commercial line and totals update. |
| T02 | QS | Add another product, section, and note line after selecting VAT. | The new commercial product line receives the same global tax selection. Sections and notes do not receive taxes. The line **Taxes** column is visible but cannot be edited. |
| T03 | QS | Select 1% Withholding while VAT remains selected. | Both configured taxes are proposed globally; no Finance approval is requested. The total reflects Odoo's normal tax calculation. |
| T04 | QS | Clear VAT, enter a genuine VAT-exemption reason, and leave withholding clear. | The draft is tax-free, the reason/audit requester/time are recorded, and Issue Offer PDF is blocked until a Quotation or Sales Manager approves the VAT exception. |
| T05 | QS | Clear VAT, enter a reason, then select 1% Withholding. | Only the existing withholding tax is proposed. Manager approval is required because VAT is absent, not because withholding is selected. |
| T06 | QS | Select neither VAT nor withholding. | No line taxes are proposed. The VAT-exemption reason and manager approval are still required before issue. |
| T07 | Quotation/Sales Manager | Approve the current VAT exemption, then change VAT status, reason, customer, product, quantity, price, discount, payment term or delivery term. | The VAT approval is invalidated by a relevant change and Issue Offer PDF is blocked again until current exceptions are approved. Restoring VAT removes the VAT-exemption approval requirement. |
| T08 | QS/Sales | Attempt to write `tax_id`, `apply_vat`, or `apply_withholding` through import/RPC or an alternate view; repeat after sending a quotation. | Individual line tax edits are rejected. Only authorized QS/Sales changes to draft header selectors succeed; sent quotation values cannot change. |
| T09 | All roles | Choose CIF or change the incoterm. | CIF is absent as a tax treatment and the selected incoterm never adds or removes VAT/withholding. No **Finance Controls** tab is present. |
| T10 | Sales/QS | From an issued quotation, confirm the Sales Order. | A mandatory confirmation popup asks whether 1% withholding applies. Cancelling makes no change. Choosing the answer already in the offer records the user/time and confirms normally. No draft invoice, `account.move`, journal entry or posting is created. |
| T11 | Sales/QS | At confirmation, choose a withholding answer different from the issued offer while every other commercial term is unchanged. | Odoo creates the next revision, applies/removes only withholding, carries valid prior commercial/VAT approvals, generates and attaches an updated Offer PDF, then confirms the revised Sales Order. No new approval is requested. |
| T12 | Sales/QS | Repeat T11 after changing price, quantity, discount, product, VAT status/reason, currency, payment term, delivery term, validity or customer. | Automatic carry-forward is rejected. Use the normal revision and approval workflow; no silent Sales Order rewrite occurs. |
| T13 | Accounting | Open a confirmed order with 1% withholding. | The withholding-evidence item is visible only to Accounting. It links the Sales Order, expected amount/rate and later invoice; Sales/QS cannot see it. Cancelling the order closes the pending item without posting entries. |
| T14 | Accounting | Use standard **Create Invoice** only after the confirmed order, then open the draft invoice. | The invoice inherits the final Sales Order taxes. Posting the invoice—not order confirmation—is when standard Odoo creates accounting entries. |
| T15 | Accounting | Repeat T01-T14 in EGP and one foreign currency, including fractional quantities/prices and a Universal Discount. | Quotations/PDFs show the expected Odoo totals. The later invoice uses the same final taxes; accounting and tax-report reconciliation follows the existing configured taxes. |

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
- standard later-invoice and tax-report reconciliation by Accounting;
- Odoo.sh warning/error review;
- portal/API/import/RPC/export evidence;
- rollback rehearsal on a disposable database.

Record each case as `Pass`, `Fail`, or `Blocked`, with database/build SHA, user, timestamp, quotation number, and evidence link. Any failure requires a new build and full rerun of the affected section plus Q09-Q10, T01-T15, and V01-V04 regression gates.
