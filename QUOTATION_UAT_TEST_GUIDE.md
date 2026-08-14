# Quotation Phase 1 - Odoo 16 UAT Guide

## Release identity

- Test only the isolated branch `codex/quotation-phase1-minimal`.
- Record the exact deployed Git SHA and Odoo.sh build number.
- Use a disposable database restored from a recent production backup; never test on `live`.
- Upgrade these modules together:
  - `egy-trade_custom`
  - `sale_discount_total`
  - `sale_order_product_pricing`
  - `sale_revision_history`
  - `sale_status_waiting_approve` if it is installed
  - `custom_create_po_from_so` for procurement regression

Before starting, take a database backup and record the number of Sales Orders in
the legacy states `approve`, `waiting`, and `waiting_approve`.

## Test users and configuration

Use separate non-administrator users for QS, Salesperson, Quotation Manager,
Sales Manager, Product Pricing, Accounting Manager, and the configured
High-Value Approver group.

Accounting must select the company's existing 14% sales VAT and existing
negative 1% sales withholding taxes in Sales Settings. Do not create or alter
taxes, accounts, tags, fiscal positions, or tax repartition rules for this test.

Sales Management must set a high-value threshold and approver group. Also test
with threshold `0`, which disables only the high-value approval requirement.

## A. Drafting and usability

| ID | Tester | Action | Expected result |
|---|---|---|---|
| A01 | QS | Create a quotation and add/edit several products, sections and notes. Save repeatedly. | Draft editing is immediate. No daily commercial-change decision or Record Commercial Change popup blocks the save. The form remains on the current quotation. |
| A02 | QS/Sales | Change to another active Sales Pricelist. | The change is allowed on Draft. Verified Pricelist-origin lines refresh; Manual Price and Product Pricing lines remain unchanged and audited. Archived pricelists are rejected. |
| A03 | QS/Sales | Try to edit a unit selling price without Product Pricing/manager authority. | The price edit is denied. Product, quantity, description, terms and allowed discounts remain editable. |
| A04 | Any Sales user | Inspect the line actions. | Add Below is not available during stabilization. Standard Add a product works without a full-page refresh or forced navigation. |
| A05 | QS | Enter Item # values. | One manual Item # column is shown; values persist and are not automatically renumbered. |

## B. Product Pricing and price origin

| ID | Tester | Action | Expected result |
|---|---|---|---|
| B01 | Ordinary QS/Sales | Open a quotation. | Product Pricing inputs, supplier estimates, factors, proposed prices, audit and margins are not visible. Price Origin is visible without revealing cost. |
| B02 | Product Pricing user | Enable Product Pricing. | A restricted input-only table appears for the same quotation lines. It shows product, quantity, Purchase Price Estimate, factors and warnings; it does not show selling prices or totals. |
| B03 | Product Pricing user | Enter estimate and factors, then Preview and close. | Preview shows the proposal but closing it changes no selling price, origin, state or audit. |
| B04 | Product Pricing user | Preview again and Confirm Apply. | Only the reviewed unchanged lines are applied atomically and the price origin/audit records Product Pricing. |
| B05 | Product Pricing user | Set Purchase Price Estimate to zero. | Product Pricing skips its formula and proposes the selected Sales Pricelist price instead of producing an accidental zero selling price. |
| B06 | Product Pricing user | Change an input after Preview, then attempt Apply. | Apply is rejected as stale; Preview must be run again. |

## C. Global quotation taxes

| ID | Tester | Action | Expected result |
|---|---|---|---|
| C01 | QS | Create a new quotation. | VAT 14% is selected by default; 1% Withholding is off. Existing configured Odoo tax records are used. |
| C02 | QS/Sales | Test VAT only, VAT plus withholding, withholding only, and neither. | Each selection is applied globally to commercial lines; sections/notes are unaffected. Line Taxes are read-only. |
| C03 | QS/Sales | Add a new product after changing the header selection. | The new line receives the current global selection through the normal fiscal-position mapping. |
| C04 | QS/Sales | Change Incoterm to CIF and back. | Incoterm never adds/removes taxes. There is no CIF tax treatment and no Finance Controls page. |
| C05 | QS/Sales | Turn VAT off without a reason, then with a reason. | Missing reason is rejected. With a reason, the requester/time are recorded and Quotation Manager approval is required before Issue Offer PDF. |
| C06 | QS/Sales | Select or clear withholding. | No Finance approval is requested. Withholding is a commercial proposal only; no invoice, journal entry or accounting evidence task is created. |
| C07 | API/import tester | Try to edit an individual line tax or protected VAT audit fields. | A line-tax write is rejected; an explicit tax on a newly created line is normalized to the header selection; protected audit fields are rejected. No bypassed line tax persists. |

## D. Approval rules

| ID | Tester | Action | Expected result |
|---|---|---|---|
| D01 | QS then Quotation Manager | Prepare a QS quotation and try Issue Offer PDF before/after approval. | Issue is blocked until the manager approves the exact current commercial snapshot. |
| D02 | Salesperson | Prepare a normal VAT-on quotation below the high-value threshold with no QS assignment. | No blanket manager or Finance approval is required. |
| D03 | Quotation Manager | Approve a QS quotation with VAT off. | One action records the manager's eligible requirements for the current snapshot. VAT reason is retained as evidence. |
| D04 | High-Value Approver | Approve a quotation exactly at and above the configured threshold. | Only a member of the configured group can approve the high-value requirement. Currency conversion uses company currency and quotation date. |
| D05 | Sales/Manager | Change customer, product, quantity, price, discount, currency, pricelist, payment/delivery terms or VAT after approval. | Applicable approval becomes invalid and Issue is blocked until the changed snapshot is approved. |
| D06 | Sales/Manager | Change only 1% withholding. | Existing QS/VAT/high-value approvals remain valid; the change is monitored, not re-approved. |
| D07 | Ordinary employee/API user | Search/read/create/write/delete approval audit rows directly. | Access or protected-operation error. Approval evidence is created only by the controlled action. |
| D08 | Administrator | Set high-value threshold to `0`. | The high-value gate is disabled; QS and VAT-off rules still operate. |

## E. Issue, lock, confirmation and accounting boundary

| ID | Tester | Action | Expected result |
|---|---|---|---|
| E01 | Authorized assigned user | Click Issue Offer PDF after required approvals. | One exact PDF is attached; actor/time/version are logged; state becomes Sent; the record and lines become immutable. It is not emailed automatically. |
| E02 | UI/import/RPC tester | Try header, line, optional-product, tax, state, copy and Send-by-Email mutations on Sent. | All normal mutation/reopen paths are blocked; create a revision instead. |
| E03 | Sales/QS | Confirm the issued offer. Cancel the popup. | Mandatory popup asks whether the customer confirmed 1% withholding. Cancel leaves the offer unchanged. |
| E04 | Sales/QS | Confirm with the same withholding choice as the issued offer. | Decision actor/time are recorded and standard Sales Order confirmation completes. No invoice or journal entry is created. |
| E05 | Sales/QS | Confirm with the opposite withholding choice and no other commercial change. | The next revision is created, only withholding changes, valid approvals carry forward once, an updated PDF is attached without email, and that revision confirms. |
| E06 | Sales/QS | Attempt automatic retention-only confirmation after any other commercial change. | Server comparison rejects carry-forward; use the normal revision and approval workflow. |
| E07 | Accounting | Later use standard Create Invoice on an invoiceable confirmed order. | A Draft invoice is created only now and inherits the final Sales Order line taxes. Standard Odoo posting creates accounting entries later. |

For E04 and E05, record `account.move` and journal-item counts immediately
before and after Sales Order confirmation; both counts must be unchanged.

## F. Revision families and migration

| ID | Tester | Action | Expected result |
|---|---|---|---|
| F01 | QS/Sales | Revise issued `S0123` three times. | Names are `S0123-01`, `S0123-02`, `S0123-03`; cumulative names are never created. |
| F02 | Any authorized Sales user | Open the normal quotation list. | Only the current family member appears. Open Revisions on it to see the original and all older versions. |
| F03 | Manager | Inspect an older cumulative chain such as `S0123-01-02`. | Existing names/PDFs remain unchanged, but the proven family is bundled and its next revision is `S0123-03`. |
| F04 | Manager | Inspect migration rows marked Revision Family Needs Review. | Ambiguous/circular/missing/conflicting families were not guessed; they remain clearly flagged for manual reconciliation. |
| F05 | Two sessions | Create the next revision from the same current issued version at nearly the same time. | Exactly one successor number is allocated; the stale request is rejected. |
| F06 | Authorized user | Restore an earlier sent family member with a reason. | A new N+1 draft is created and audited; no issued historical record or PDF is changed. |

## G. Legacy state and procurement regression

| ID | Tester | Action | Expected result |
|---|---|---|---|
| G01 | Administrator | Upgrade a copy containing `approve`, `waiting`, and `waiting_approve` orders. | They map to Draft with a chatter note. The standard state bar contains no custom approval states. |
| G02 | API tester | Call legacy `action_to_approve` and `action_approve`. | They cannot confirm, reopen or create a custom state. |
| G03 | Product Pricing/Procurement | Generate service and MTO RFQs with a non-zero saved estimate. | Existing procurement behavior and saved-rate provenance remain correct. |
| G04 | Procurement | Generate an RFQ with zero estimate and a positive vendor price, then with neither. | Vendor price is retained in the first case; Supplier Cost Required blocks PO confirmation in the second until cost/reason are supplied. |

## Release stop conditions

Do not promote if any of the following is missing:

- clean upgrade of every listed module;
- complete automated module suite with zero failures/errors;
- all cases above tested with non-admin role users;
- migration counts and ambiguous-family list captured;
- no invoice/journal entry created by Sales Order confirmation;
- later standard invoice tax inheritance reconciled by Accounting;
- exact build SHA, database backup identifier, screenshots and failure notes;
- rollback rehearsal using commit revert plus the matching pre-upgrade backup.

Any failure requires a new build and rerun of the affected section plus C, D, E
and F regression cases.
