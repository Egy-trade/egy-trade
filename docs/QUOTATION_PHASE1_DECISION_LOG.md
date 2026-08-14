# Quotation Phase 1 Decision Log

| Metadata | Value |
|---|---|
| Status | Implemented on isolated branch; staging verification pending |
| Decision date | 2026-08-14 |
| Reviewed source branch | `codex/quotation-uat-completion` |
| Reviewed commit | `66210cb` |
| Implementation approach | Create a new minimal-stabilization branch from `66210cb` and simplify forward |
| Implementation branch | `codex/quotation-phase1-minimal` |
| Related future backlog | `docs/QUOTATION_FUTURE_PHASES_BACKLOG.md` |

## Purpose

This document records the current Phase 1 business decisions and the technical
reasoning needed to implement or reverse them later. It is a decision record,
not permission to change production, accounting configuration, tax records, or
the Odoo.sh database without the normal staging and backup gates.

## D-001: Implementation Baseline and Reversibility

### Decision

Preserve `codex/quotation-uat-completion` at reviewed commit `66210cb`. Create a
new branch from that commit for the reduced Phase 1 implementation. Do not reset
the existing branch to `c551447` and do not attempt an in-place database
downgrade.

### Reason

The current module version and migrations may already have run on staging.
Odoo upgrades forward; checking out older code does not automatically reverse
fields, migrated values, approval records, or database columns. Starting from
the reviewed head preserves later pricing, security, lifecycle, and test fixes
while allowing unwanted enforcement to be removed through explicit forward
changes.

### Evidence to capture before implementation

- Exact Git SHA deployed on the isolated staging branch.
- Installed module versions on the staging database.
- Installed status of the modules that override Sales Order confirmation or
  approval.
- Counts of Sales Orders in each custom and standard state.
- A database backup or production-derived disposable staging snapshot.
- Existing active quotation families whose names or links are ambiguous.

The implementer will collect and record this evidence. It is not a technical
decision that must be delegated to the business user.

### Rollback rule

Rollback means reverting the Phase 1 commits and, if a migration changed data,
restoring the matching pre-upgrade database backup. It does not mean checking
out an older module version against a newer database.

## D-002: Revision Families and Names

### Agreed behavior

All revisions of the same quotation must appear as one family, including
quotations created before the new implementation.

- The original quotation keeps the root number, for example `S0123`.
- Its revisions are `S0123-01`, `S0123-02`, `S0123-03`, and so on.
- Revision suffixes are always calculated from the root number.
- Cumulative names such as `S0123-01-02` or `S0123-01-02-03` are forbidden.
- Creating a revision from any member of the family must allocate the next
  unused family sequence under `S0123`.
- The main quotation list shows only the current revision.
- The current quotation contains a Revisions action/list showing the original
  and every previous revision, newest first.

### Historical records

Older quotations will be linked into families using existing revision links
and revision metadata first. Name parsing is only a controlled fallback because
a hyphen in a legitimate quotation number must not be mistaken for a revision.

Issued historical quotation names and attached PDFs must not be silently
renamed. Their original legal/audit reference is preserved. The family can
display a normalized revision sequence separately, and all future revisions
use the correct root-based name.

### Required safeguards

- Lock the family while allocating the next sequence to prevent two users from
  receiving the same revision number.
- Enforce one current revision per family.
- Produce a migration reconciliation report listing linked, ambiguous, and
  unlinked historical quotations.
- Never guess an ambiguous family silently.

## D-003: Quotation Approvals and Monitoring

### Finance responsibility

Finance must not operate a general blocking approval workflow during quotation
preparation. Payment terms, expiry, incoterms, manual prices, withholding, and
ordinary commercial changes are not Finance approval gates.

Finance may receive non-blocking monitoring information or activities. A
monitoring activity cannot prevent saving, issuing, revising, or confirming a
quotation.

### Blocking approvals retained in Phase 1

Only the following blocking approvals remain:

1. **QS quotation approval:** A quotation prepared by a Quotation Specialist
   must be approved by a Quotation Manager before `Issue Offer PDF`.
2. **VAT-off approval:** A quotation with VAT disabled requires a reason and
   Quotation Manager approval before `Issue Offer PDF`.
3. **High-value approval:** A quotation at or above a configurable company
   threshold requires approval by the configured High-Value Approver group.

The high-value threshold must be stored in company Sales settings, not hard
coded. Comparison must use a defined company currency and the quotation date's
currency conversion. Setting the threshold to zero may disable this gate if
the final settings design states that clearly.

Finance is not hard coded as the high-value approver. The configured approver
group can include Finance, Directors, Owners, or designated managers according
to company policy without changing code.

### Approval implementation rule

Approvals must not introduce another `sale.order.state`. The Sales Order keeps
the standard Odoo Draft, Sent, Sales Order, Locked, and Cancelled lifecycle.
Approval is a separate status/evidence record tied to the commercial snapshot
that was reviewed.

The Phase 1 workflow must resolve the existing competing `approve`, `waiting`,
`action_confirm`, and `action_approve` implementations before other release
work is accepted.

### Approval invalidation and carry-forward

Material commercial changes after approval require a new applicable approval.
Examples include product, quantity, unit price, discount, currency, pricelist,
payment terms, delivery terms, or VAT selection.

A withholding-only change does not invalidate Quotation Manager or high-value
approval. It is recorded and monitored, and the revision remains in the same
family. No new approval is requested when server-side comparison proves that
withholding is the only commercial difference.

## D-004: Access Rights Scope

The comprehensive access-rights redesign is deferred to the next phase. This
includes company-wide safe quotation visibility, similarity warnings, revised
QS/Sales confidentiality rules, Lighting Designer access, CRM ownership of
drawings, exports, direct URLs, and the full role matrix.

Phase 1 may still make the minimum access corrections required to operate the
stabilized workflow safely:

- QS and Sales can create and edit ordinary assigned drafts and choose the
  relevant standard Sales Pricelist.
- A Quotation Manager can review and approve QS quotations.
- Product Pricing inputs, cost, factors, and margins remain hidden from users
  who are not eligible for Product Pricing.
- Server-side protections remain effective through UI, import, and RPC paths.

These minimum corrections are not the deferred company-wide access redesign.

## D-005: Phase 1 Removal and Retention Boundaries

### Keep

- Price Origin and append-only pricing audit.
- Purchase Price Estimate and pricing factors for eligible users.
- Secure Product Pricing Preview and Apply.
- Explicit Issue Offer PDF, attached issued document, Sent lock, and revisions.
- Global VAT and withholding selection using existing Odoo taxes.
- Retention-only approval carry-forward after server-side comparison.
- Basic discount cap and zero-price/FOC protection.
- Standard Sales Order confirmation with no automatic invoice or journal entry.

### Remove or make non-blocking

- Daily Record Commercial Change gate on draft editing.
- Broad Finance approval requirements.
- CIF tax automation.
- Quotation-level custom accounting and withholding-evidence enforcement.
- Visible duplicate Product Pricing line grid.
- Competing custom Sales Order approval states.

### Defer

- Full access-rights redesign.
- Discount tiers, gross-margin floors, and Director exception design.
- CRM drawings and Lighting Designer assignment redesign.
- Company-wide quotation directory and similarity warnings.
- Accounting withholding-evidence activities.
- No-refresh and active-line UI refinements.
- Odoo 19 replacements and migration implementation.

## D-006: Acceptance and Change Log Requirements

Every implementation decision must be reversible and attributable:

- one focused commit for Sales Order state/approval collision repair;
- one focused commit for removal of draft-editing blockers;
- one focused commit for Finance-control reduction;
- separate revision-family migration and reconciliation evidence;
- module versions increased only forward;
- migration output and ambiguous historical records recorded;
- full automated tests followed by role-based browser UAT on isolated staging;
- final deployed SHA and database backup identifier recorded here or in the
  release handoff.

Any later decision that changes these rules must append a dated entry below;
it must not silently rewrite the original decision.

## Decision Changes

### 2026-08-14

- Selected forward simplification from `66210cb` rather than restarting from
  `c551447`, subject to recording the actual staging SHA and installed module
  versions before implementation.
- Required root-based revision names and historical family bundling.
- Removed normal Finance blocking approvals; retained configurable high-value
  approval and non-blocking Finance monitoring.
- Confirmed Quotation Manager approval before issuing QS quotations.
- Deferred the comprehensive access-rights redesign to the next phase.
