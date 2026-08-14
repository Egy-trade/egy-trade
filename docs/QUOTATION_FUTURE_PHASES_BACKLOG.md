# Quotation Future Phases Backlog

| Metadata | Value |
|---|---|
| Status | Future phases â€” do not implement during stabilization |
| Source branch | `codex/quotation-uat-completion` |
| Reviewed commit | `66210cb` |
| Decision record date | 2026-08-14 |
| Immediate priority | Stabilize Odoo 16 and remove workflow blockers |

## Purpose

This document preserves the quotation improvements discussed after the current
Odoo 16 build was reviewed. These items are intentionally separated from the
immediate stabilization release so that the team can first remove blocking
behavior, restore a practical drafting workflow, and prove the essential
quotation controls on staging.

This is a design and decision record only. It does not authorize production
code, migrations, tax/accounting changes, staging configuration, or Odoo 19
migration work.

## Relationship to Phase 1 Stabilization

Phase 1 is limited to removing blockers and retaining only the controls needed
to create, issue, revise, and confirm a correct quotation. In particular, Phase
1 should resolve competing Sales Order states and approval paths, remove the
daily commercial-change gate, restore QS/Sales pricelist selection, remove the
visible duplicate Product Pricing grid, and verify the existing pricing, tax,
PDF, lock, revision, and procurement flows.

The features below must not expand Phase 1. They should be implemented only
after the reduced workflow passes full Odoo tests and role-based browser UAT.

## Agreed Future Design

### 1. Quotation revision presentation

- The normal Quotations list shows only the newest active revision, for example
  `S03652-02`.
- The current quotation exposes a `Revisions (n)` smart button containing the
  earlier read-only records, such as `S03652` and `S03652-01`, newest first.
- Searching for an earlier quotation number should lead the user to the current
  quotation family and identify the matching historical revision.
- Issued revisions remain immutable. A commercial change creates the next
  revision rather than reopening an issued record.

### 2. Roles and commercial visibility

#### QS and Sales

- QS and Sales share the same operational quotation permissions.
- They may create and edit assigned draft quotations, select products,
  quantities, descriptions, terms, taxes, and authorized discounts.
- They may select among approved Sales Pricelists assigned to their Sales Team
  or discount tier.
- They cannot type or override selling prices, expose or edit internal pricing
  fields, run Product Pricing, or see purchase costs, factors, or margins.
- They receive generic commercial-policy messages that do not reveal the
  affected product, cost, floor, or margin.

#### Quotation Manager

- The Quotation Manager can view and edit complete quotations.
- Sensitive price, discount, VAT-exemption, and commercial-term changes require
  a justification and immutable audit entry.
- Normal verified-pricelist quotations do not require blanket approval.
- Manager approval is required only for configured exceptions, including VAT
  off, a discount above the user's authority, and zero-price/FOC cases.
- Manager authority stops at the company hard ceiling. An Owner/Director may
  approve an explicit exception above that ceiling with a reason and exact-line
  audit evidence.

#### Product Pricing

- Product Pricing users and Quotation Managers may see purchase estimates,
  cost currencies, factors, proposed prices, margin/floor information, and
  protected pricing warnings.
- Product Pricing remains an optional pricing path. A quotation may contain a
  mixture of verified Pricelist lines and Product Pricing lines.
- QS/Sales may request Product Pricing but cannot execute it or view its
  internal data.

#### Lighting Designer

- Lighting Designer access is driven by CRM opportunity assignment, not direct
  access to `sale.order`.
- An assigned designer may see customer organization, project name/reference,
  current quotation/revision status, products, descriptions, quantities, and
  released technical drawings.
- The designer must not see named customer contacts, phone/email/address,
  selling prices, totals, discounts, taxes, payment/delivery terms, purchase
  costs, factors, margins, or customer commercial PDFs.

### 3. Team-assigned Sales Pricelists

- Sales Settings assigns approved active pricelists to Sales Teams or user
  tiers. Quotation Managers may use all active company Sales Pricelists.
- Changing pricelist on a draft reprices only verified Pricelist-origin lines.
- Product Pricing and authorized Manual Price lines remain protected.
- Discounts and exception approvals are re-evaluated against the new reference
  prices.
- A pricelist change after Issue Offer requires a revision.
- Currency/pricelist changes must preserve the current form tab, line page,
  scroll position, and active row.

### 4. Safe company-wide quotation discovery

- QS/Sales do not receive read access to other users' complete Sales Orders.
- A safe company quotation directory shows customer organization, project,
  current quotation/revision, status, owner, important dates, and non-commercial
  product family/brand summaries.
- It excludes prices, totals, discounts, quantities, tax choices, named
  contacts, internal pricing evidence, and attachments.
- CRM opportunities show their existing quotation families before a user
  starts another offer.
- Selecting customer/project on a new quotation triggers similarity warnings
  for the same CRM opportunity, same customer/project, or overlapping product
  families.
- Similarity remains advisory. Users may create another quotation after seeing
  the warning; the system records the duplicate warning result for monitoring.

### 5. CRM ownership of drawings and technical assignments

- CRM Opportunity becomes the owner of Lighting Designer assignments,
  drawings, drawing revisions, release status, and technical notes.
- All quotation revisions linked to the same opportunity reference the CRM
  technical documents instead of copying them into each quotation.
- The CRM technical workspace shows each quotation family's newest technical
  scope where an opportunity has more than one family.
- Only released drawings are available to assigned Lighting Designers.
- Drawing release requires human confirmation that the file and its metadata do
  not expose prices, margins, customer contacts, or other commercial content.

### 6. Product Pricing Queue and review experience

The current build provides a Product Pricing tab inside each quotation, a
second line grid (`pricing_line_ids`), and a Preview/Apply modal. The future
design retains the secure calculation and atomic Preview/Apply behavior but
removes the duplicate quotation grid.

The future Product Pricing experience has two parts:

1. A Product Pricing Queue lists quotations requiring attention, including the
   requester, customer organization/project, current quotation, product types,
   missing-cost count, warning count, assigned Pricing user, age, and status.
2. A deliberate Review Product Pricing modal, opened from the queue or current
   quotation, shows authorized users the real cost/factor/proposed-price data
   without adding a second persistent line grid to the quotation form.

Preview remains non-mutating. Apply remains atomic, evidence-backed, and
audited. Closing the modal returns the user to the same quotation tab, line
page, scroll position, and focused row.

### 7. Zero purchase-cost fallback

- When Purchase Price Estimate is greater than zero, Product Pricing calculates
  the proposed selling price using the verified cost and configured factors.
- When Purchase Price Estimate is zero and the Sales Pricelist returns a
  non-zero price, Product Pricing is skipped and the Sales Pricelist price is
  used with Price Origin `Pricelist`.
- The Sales Pricelist selling price must never be stored or treated as purchase
  cost.
- Missing cost is visible only to eligible Product Pricing users and Managers
  and may propagate to Procurement as `Supplier Cost Required`.
- If both purchase estimate and Sales Pricelist price are zero, Issue Offer is
  blocked as `Selling Price Required`, unless the line follows the explicit FOC
  process.

### 8. Discount Authority Tiers

- Replace individually maintained discount caps with editable Discount
  Authority Tiers, such as Trainee, Standard Sales, Senior Sales, and Manager.
- Promotion changes the user's assigned tier rather than silently editing a
  personal limit.
- Each tier defines a without-approval ceiling and a with-Quotation-Manager
  ceiling. The company also defines a hard ceiling.
- Owner/Director exceptions above the hard ceiling require a reason, exact
  affected lines, actor/time, and resulting commercial evidence.
- Tier changes and assignments are audited.
- The tier rules apply to the compounded final discount rather than only one
  visible discount field.

### 9. Global and item discount behavior

- Retain the current header-level Global Discount concept because it distributes
  the discount onto lines and carries it downstream instead of creating an
  unrelated negative product line.
- Rename the user-facing concepts to `Item Discount` and `Quotation Discount`;
  internal field names such as `discount_2` and `discount_3` must not be shown.
- Apply Global Discount server-side consistently through the UI, imports, and
  RPC; onchange behavior alone is not an authority boundary.
- Newly added eligible lines inherit the active quotation discount without a
  disruptive form reload.
- Discounts are evaluated after compounding item and quotation discounts.
- A normal quotation line must remain independently commercially safe. A
  profitable line must not subsidize a loss-making line.
- Deliberate package/cross-subsidy pricing is deferred and is not part of the
  normal workflow.

### 10. Configured pricing floors and protected messages

- Pricing floors belong in company Sales/Pricing Settings rather than being
  freely reduced on individual projects.
- Pricelist-origin prices must also be compared with verified cost when a cost
  exists; an approved Sales Pricelist does not by itself prove current margin.
- The quotation-level overall margin is useful for monitoring but must not hide
  an unsafe individual line.
- When a requested discount breaches policy, QS/Sales receive only a generic
  message and a Quotation Manager activity is created.
- Protected detail visible only to Product Pricing users and Managers includes
  product type/category, line reference, Price Origin, configured floor,
  requested final price/deviation, missing-cost status, resulting margin, and
  recommended safe discount.
- Protected pricing details must not be posted into normal quotation chatter.

### 11. No-refresh quotation UX

- Normal save, product selection, quantity/UoM change, pricelist selection,
  VAT/withholding change, discount application, and line editing must not
  navigate away from the current form.
- Preserve the active notebook tab, one2many pager, vertical/horizontal scroll,
  selected row, and inline editor focus.
- Server data may be refreshed internally, but the refresh must be invisible to
  the user and restore the exact working position.
- `Add Below` must insert and focus a normal line in place rather than return a
  full-form navigation action.
- Navigation is acceptable only when creating a genuinely new revision or
  completing Sales Order confirmation.

### 12. Accounting ownership of withholding evidence

- VAT and withholding selections remain commercial proposal fields on the
  quotation/Sales Order.
- Sales Order confirmation creates no invoice or journal entry.
- When withholding applies, Accounting receives an activity/document request
  associated with the later invoice/payment process.
- Withholding certificates, remittance references, dates, and reconciliation
  evidence belong on Accounting documents or their linked Documents records,
  not on the quotation form.

## Deliberately Deferred from Stabilization

- Discount Authority Tier models and migration from current personal caps.
- Gross-margin floor engine and Director exception workflow.
- Hardened mixed-origin Global Discount eligibility.
- Product Pricing Queue.
- Safe company quotation directory and similarity engine.
- Team-assigned pricelist configuration.
- CRM migration of drawings and Lighting Designer assignments.
- Accounting activity/document workflow for withholding evidence.
- Advanced client-side preservation of pager, scroll, and active-line state.
- In-place `Add Below` redesign.
- Package-pricing or deliberate loss-leader functionality.
- Odoo 19 rewrites or migrations.

## Unresolved Decisions

These items require business evidence or a focused design decision before their
future phase begins:

1. **Gross-margin floor structure:** Minimum gross margin was preferred over a
   minimum factor, and it must include Pricelist-origin lines compared with
   cost. It remains unresolved whether settings use one company default plus
   category overrides, how categories inherit, and which cost basis is reliable
   enough to call the result gross margin.
2. **Evaluation granularity:** The no-subsidy decision strongly favors checking
   every line independently while showing quotation margin only as a summary.
   This needs formal confirmation before implementation.
3. **Missing-cost discount policy:** When cost is missing but the approved Sales
   Pricelist returns a non-zero price, decide whether the full price may issue
   with no discount, whether Issue must be blocked, or whether tier discounts
   remain permitted.
4. **Fixed-amount discount:** Decide whether fixed quotation discounts are
   removed, restricted to Managers/Directors, or implemented later as explicit
   package pricing.
5. **Safe-directory product detail:** Confirm whether other QS/Sales users see
   product family/brand summaries only or exact product names without quantities.
6. **Similarity horizon and matching:** Define the date horizon, project-name
   normalization, and product overlap required to show a warning.

## Odoo 19 Verification and Probable Disposition

No Odoo 19 feature should be treated as a replacement until it passes a clean
Enterprise sandbox parity test.

### Probable standard replacements

- CRM activities, qualification, ownership, and handover.
- Documents storage, document requests, and technical-file organization.
- PDF Quote Builder for branded pages and product technical PDFs.
- Quotation templates and normal validity defaults.
- Standard line/global discount presentation where it satisfies the approved
  authority and margin rules.
- Studio button approval rules where they support reasons, invalidation, and
  the required segregation of duties.
- Standard taxes, fiscal positions, Egyptian localization, and negative
  withholding-tax configuration.
- Normal currency conversion and standard margin reporting.

### Likely custom retention or rewrite

- Verified Price Origin, protected reference price, and immutable pricing audit.
- Manual-price preservation during Odoo price recomputation.
- Exact issued-PDF snapshot, Sent immutability, and quotation revision family if
  Odoo 19 does not provide equivalent behavior.
- Product Pricing based on verified purchase estimate and EGYTRADE factors.
- Discount Authority Tiers, per-line margin floors, protected exception detail,
  and Director overrides.
- Retention-only comparison and approval carry-forward.
- Purchase estimate provenance and Supplier Cost Required controls.
- Safe company quotation projection where standard CRM visibility cannot meet
  the confidentiality requirement.

### Required Odoo 19 parity checks

- Immutable issued PDF with actor/time and controlled email behavior.
- Supported quotation revision/version behavior.
- Conditional approval rules with reasons and relevant-field invalidation.
- Pricelist recomputation without overwriting protected negotiated prices.
- Per-user/tier discount authority and per-line margin enforcement.
- Withholding behavior on quotation, invoice, journal entry, tax report, and
  Egyptian ETA output.
- CRM/Documents permissions for assigned Lighting Designers.
- Stable Purchase/MTO/service extension points for cost provenance.
- Portal, RPC, import, export, and non-admin field-leakage tests.

## Decision Log

| Topic | Status | Decision |
|---|---|---|
| Immediate release scope | Agreed | Stabilize first; defer fine-tuning |
| Revision list | Agreed | Show only newest revision; history inside current record |
| QS/Sales permissions | Agreed | Same operational capability; no price editing/internal pricing |
| Pricelist selection | Agreed | Team-assigned approved lists in future phase |
| Company-wide visibility | Agreed | Safe directory, never masked access to full quotations |
| Similar quotations | Agreed | Warning only; do not block creation |
| Drawings | Agreed | Move ownership and assignment to CRM |
| Lighting Designer identity | Agreed | Customer organization only; no named contacts |
| Product Pricing | Agreed | Secure role plus Manager; queue and modal, no duplicate grid |
| Zero purchase cost | Agreed | Skip formula and use non-zero Sales Pricelist price |
| Discount administration | Agreed | Editable user tiers with promotion by tier assignment |
| Manager ceiling | Agreed | Director exception above company hard ceiling |
| Cross-subsidy | Agreed | Not allowed in normal quotation workflow |
| Discount rejection visibility | Agreed | Generic QS/Sales message; protected Pricing/Manager detail |
| Pricing floor location | Agreed | Company settings, not project-controlled |
| Pricing floor metric | Partially agreed | Prefer minimum gross margin; exact structure unresolved |
| Missing-cost discounts | Unresolved | Requires explicit policy before Phase 2 |
| Fixed-amount/package discount | Deferred | Excluded from stabilization |
| Draft commercial changes | Agreed | Free draft editing; revision only after Issue |
| Withholding evidence | Agreed | Accounting activity/documents, not quotation tab |
| Sales responsibility | Agreed | CRM ownership and handover |
| No-refresh UX | Agreed | Preserve working position during ordinary editing |
