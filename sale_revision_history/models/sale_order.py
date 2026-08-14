# -*- coding: utf-8 -*-
"""Safe, auditable quotation revisions.

A revision never reopens or mutates the quotation that was sent.  It creates a
new draft and keeps every superseded quotation as an inactive historical
record in the same revision family.
"""

import base64
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.sale_order_product_pricing.models.sale_order import (
    _PRICING_INTERNAL_TOKEN,
    _is_pricing_downpayment,
    _is_pricing_internal,
)
from odoo.addons.sale_order_product_pricing.models.finance_controls import (
    _is_finance_internal,
    _RETENTION_REVISION_TOKEN,
)
from odoo.addons.sale_order_product_pricing.models.sale_order_offer_dates import (
    _RETENTION_DATE_COPY_TOKEN,
)


_REVISION_INTERNAL_TOKEN = object()
_LIFECYCLE_INTERNAL_TOKEN = object()
_LIFECYCLE_INITIALIZING_TOKEN = object()
_LIFECYCLE_CONFIRMING_TOKEN = object()
_WITHHOLDING_CONFIRMATION_TOKEN = object()
_REVISION_SYSTEM_FIELDS = {
    "current_revision_id",
    "revision_number",
    "unrevisioned_name",
    "revision_reason",
    "revision_date",
    "revision_author_id",
    "restored_from_revision_id",
    "restoration_reason",
    "restoration_date",
    "restoration_author_id",
    "restoration_difference_summary",
    "withholding_confirmation",
    "withholding_confirmation_at",
    "withholding_confirmation_by",
    "retention_only_revision",
    "retention_only_source_id",
    "revision_family_ambiguous",
    "revision_family_ambiguity_reason",
}

_REVISION_SUFFIX_RE = re.compile(r"(?:-\d{2})+$")


def _is_revision_internal(env):
    """Only in-process revision operations may write family metadata."""
    return env.context.get("_revision_internal_token") is _REVISION_INTERNAL_TOKEN


def _is_lifecycle_internal(env):
    return env.context.get("_lifecycle_internal_token") is _LIFECYCLE_INTERNAL_TOKEN


def _is_lifecycle_initializing(env):
    return env.context.get(
        "_lifecycle_initializing_token"
    ) is _LIFECYCLE_INITIALIZING_TOKEN


def _is_lifecycle_confirming(env):
    return env.context.get(
        "_lifecycle_confirming_token"
    ) is _LIFECYCLE_CONFIRMING_TOKEN


def _is_withholding_confirmation(env):
    """True only for the in-process confirmation wizard action.

    A Python object token cannot be supplied through an HTTP/RPC context, so a
    caller cannot use ``action_confirm`` to bypass the mandatory dialog.
    """
    return env.context.get(
        "_withholding_confirmation_token"
    ) is _WITHHOLDING_CONFIRMATION_TOKEN


class SaleOrder(models.Model):
    _inherit = "sale.order"

    current_revision_id = fields.Many2one(
        "sale.order", string="Current Revision", readonly=True, copy=False,
        index=True,
    )
    old_revision_ids = fields.One2many(
        "sale.order", "current_revision_id", string="Previous Revisions",
        readonly=True, context={"active_test": False},
    )
    revision_number = fields.Integer(string="Revision", readonly=True, copy=False)
    unrevisioned_name = fields.Char(
        string="Revision Family", readonly=True, copy=False, index=True,
    )
    revision_reason = fields.Text(
        string="Revision Comment", readonly=True, copy=False,
        help="Why this successor revision was created and what changed.",
    )
    revision_date = fields.Datetime(
        string="Revised On", readonly=True, copy=False, index=True,
    )
    revision_author_id = fields.Many2one(
        "res.users", string="Revised By", readonly=True, copy=False, index=True,
    )
    restored_from_revision_id = fields.Many2one(
        "sale.order", string="Restored From", readonly=True, copy=False, index=True,
        help="The previously sent quotation version copied into this new draft.",
    )
    restoration_reason = fields.Text(
        string="Restoration Reason", readonly=True, copy=False,
        help="Why a historical sent quotation was restored into a new draft.",
    )
    restoration_date = fields.Datetime(
        string="Restored On", readonly=True, copy=False, index=True,
    )
    restoration_author_id = fields.Many2one(
        "res.users", string="Restored By", readonly=True, copy=False, index=True,
    )
    restoration_difference_summary = fields.Text(
        string="Restoration Audit", readonly=True, copy=False,
        help="The source, actor, reason, totals, and commercial snapshot difference recorded at restoration.",
    )
    active = fields.Boolean(default=True, copy=True)

    commercial_change_date = fields.Date(
        string="Commercial Change Date", readonly=True, copy=False,
        help="Legacy audit data retained for historical quotations; it no longer controls draft editing.",
    )
    commercial_change_decision = fields.Selection(
        [("update_today", "Update Today"), ("create_revision", "Create Revision")],
        string="Commercial Change Decision", readonly=True, copy=False,
        help="The recorded decision for the latest commercial change.",
    )
    commercial_change_decision_at = fields.Datetime(
        string="Commercial Decision At", readonly=True, copy=False,
    )
    commercial_change_decision_by = fields.Many2one(
        "res.users", string="Commercial Decision By", readonly=True, copy=False,
    )
    commercial_change_audit = fields.Text(
        string="Commercial Change Audit", readonly=True, copy=False,
    )
    issued_offer_attachment_id = fields.Many2one(
        "ir.attachment", string="Issued Offer PDF", readonly=True, copy=False,
        help="Exact customer PDF attached when this quotation was issued.",
    )
    issued_offer_at = fields.Datetime(
        string="Issued At", readonly=True, copy=False,
    )
    issued_offer_by = fields.Many2one(
        "res.users", string="Issued By", readonly=True, copy=False,
    )
    issued_offer_version = fields.Char(
        string="Issued Version", readonly=True, copy=False,
    )
    issued_offer_audit = fields.Text(
        string="Issue Offer Audit", readonly=True, copy=False,
    )
    sales_responsibility_accepted = fields.Boolean(
        string="Sales Responsibility Accepted", readonly=True, copy=False,
        help="Set when the assigned Salesperson accepts responsibility for this draft quotation.",
    )
    sales_responsibility_accepted_at = fields.Datetime(
        string="Sales Responsibility Accepted At", readonly=True, copy=False,
    )
    sales_responsibility_accepted_by = fields.Many2one(
        "res.users", string="Sales Responsibility Accepted By", readonly=True, copy=False,
    )
    issued_without_sales_acceptance = fields.Boolean(
        string="Issued Without Sales Acceptance", readonly=True, copy=False,
        help="KPI flag: the offer was issued before assigned Sales accepted responsibility.",
    )
    withholding_confirmation = fields.Selection(
        [("yes", "Customer confirmed 1% withholding"),
         ("no", "Customer did not confirm 1% withholding")],
        string="Withholding Confirmation", readonly=True, copy=False,
    )
    withholding_confirmation_at = fields.Datetime(
        string="Withholding Confirmed At", readonly=True, copy=False,
    )
    withholding_confirmation_by = fields.Many2one(
        "res.users", string="Withholding Confirmed By", readonly=True, copy=False,
    )
    retention_only_revision = fields.Boolean(
        string="System Retention-only Revision", readonly=True, copy=False,
        help="A system-generated revision where 1% withholding was the only changed term.",
    )
    retention_only_source_id = fields.Many2one(
        "sale.order", string="Retention-only Source", readonly=True, copy=False,
    )
    revision_family_ambiguous = fields.Boolean(
        string="Revision Family Needs Review", readonly=True, copy=False,
        index=True,
        help="Set only by the migration when existing revision metadata conflicts. "
             "The records are deliberately not guessed into a family.",
    )
    revision_family_ambiguity_reason = fields.Text(
        string="Revision Family Review Reason", readonly=True, copy=False,
    )

    def _commercial_fingerprint(self):
        """Stable comparison of every agreed commercial value except withholding.

        This deliberately includes VAT selection/reason, counterparties, terms,
        product rows, optional products and price-origin evidence.  Calculated
        totals and ``apply_withholding`` are omitted: both necessarily change in
        a valid withholding-only revision.
        """
        self.ensure_one()

        def ordered(records):
            """Order virtual onchange records without comparing ``NewId`` objects."""
            def key(index_and_record):
                index, record = index_and_record
                record_id = record.id
                # Odoo's in-memory onchange rows use NewId objects, which
                # cannot be ordered against persisted integer ids.  The
                # recordset order is the stable tie-breaker for those rows.
                return (
                    record.sequence or 0,
                    record_id if type(record_id) is int else 0,
                    index,
                )

            return (record for _index, record in sorted(
                enumerate(records), key=key,
            ))

        def ref(record):
            return record.id or False
        configured_withholding = getattr(
            self.company_id, "quotation_retention_tax_id", self.env["account.tax"],
        )
        effective_tax = getattr(self, "_quotation_effective_tax", None)
        withholding_tax = (
            effective_tax(configured_withholding)
            if effective_tax else configured_withholding
        )
        lines = []
        for line in ordered(self.order_line):
            lines.append({
                "sequence": line.sequence, "display_type": line.display_type or False,
                "product": ref(line.product_id), "name": line.name or "",
                "quantity": line.product_uom_qty, "uom": ref(line.product_uom),
                "price_unit": line.price_unit, "discount": line.discount,
                "discount_2": getattr(line, "discount_2", 0.0),
                "discount_3": getattr(line, "discount_3", 0.0),
                "non_withholding_tax_ids": sorted((line.tax_id - withholding_tax).ids),
                "sn": getattr(line, "sn", False) or False,
                "purchase_price_estimate": getattr(line, "purchase_price_estimate", 0.0),
                "factor": getattr(line, "factor", 0.0),
                "line_factor": getattr(line, "line_factor", 0.0),
                "price_origin": getattr(line, "price_origin", False) or False,
                "price_origin_verified": getattr(line, "price_origin_verified", False),
                "price_origin_evidence": getattr(line, "price_origin_evidence", False) or False,
                "price_reference": getattr(line, "price_reference", 0.0),
                "price_currency": ref(getattr(line, "price_currency_id", self.env["res.currency"])),
                "is_free_of_charge": getattr(line, "is_free_of_charge", False),
                "free_of_charge_reason": getattr(line, "free_of_charge_reason", False) or False,
            })
        options = []
        for option in ordered(self.sale_order_option_ids):
            options.append({
                "sequence": option.sequence, "product": ref(option.product_id),
                "name": option.name or "", "quantity": option.quantity,
                "uom": ref(option.uom_id), "price_unit": option.price_unit,
                "discount": getattr(option, "discount", 0.0),
            })
        return {
            "partner": ref(self.partner_id), "partner_invoice": ref(self.partner_invoice_id),
            "partner_shipping": ref(self.partner_shipping_id), "currency": ref(self.currency_id),
            "pricelist": ref(self.pricelist_id), "fiscal_position": ref(self.fiscal_position_id),
            "payment_term": ref(self.payment_term_id), "incoterm": ref(self.incoterm),
            "warehouse": ref(self.warehouse_id), "salesperson": ref(self.user_id),
            "company": ref(self.company_id),
            "quotation_specialist": ref(getattr(self, "quotation_specialist_id", self.env["res.users"])),
            "client_order_ref": self.client_order_ref or "", "note": self.note or "",
            "offer_date": str(self.offer_date or ""), "validity_date": str(self.validity_date or ""),
            "offer_expiry_days": getattr(self, "offer_expiry_days", 0),
            "commitment_date": str(self.commitment_date or ""),
            "template": ref(self.sale_order_template_id), "apply_vat": getattr(self, "apply_vat", True),
            "vat_exemption_reason": getattr(self, "vat_exemption_reason", False) or False,
            "product_pricing": getattr(self, "product_pricing", False),
            "estimate_currency": ref(getattr(self, "currency_estimate_id", self.env["res.currency"])),
            "estimate_rate": getattr(self, "currency_rate_estimate", 0.0),
            "estimate_inverse_rate": getattr(self, "currency_rate_inverse", 0.0),
            "rate_change_type": getattr(self, "change_currency_rate_type", False) or False,
            "rate_change": getattr(self, "change_currency_rate", 0.0),
            "global_factor": getattr(self, "global_factor", 0.0),
            "global_discount_enabled": getattr(self, "ks_enable_discount", False),
            "global_discount_type": getattr(self, "ks_global_discount_type", False) or False,
            "global_discount_rate": getattr(self, "ks_global_discount_rate", 0.0),
            "header_discount_type": getattr(self, "discount_type", False) or False,
            "header_discount_rate": getattr(self, "discount_rate", 0.0),
            "lines": lines, "options": options,
        }

    @staticmethod
    def _fingerprint_difference_paths(expected, actual, prefix=""):
        """Return field paths only, never confidential commercial values."""
        if isinstance(expected, dict) and isinstance(actual, dict):
            paths = []
            for key in sorted(set(expected) | set(actual)):
                path = "%s.%s" % (prefix, key) if prefix else key
                if key not in expected or key not in actual:
                    paths.append(path)
                else:
                    paths.extend(SaleOrder._fingerprint_difference_paths(
                        expected[key], actual[key], path,
                    ))
            return paths
        if isinstance(expected, list) and isinstance(actual, list):
            paths = []
            if len(expected) != len(actual):
                paths.append("%s.length" % prefix)
            for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
                paths.extend(SaleOrder._fingerprint_difference_paths(
                    expected_item, actual_item, "%s[%d]" % (prefix, index),
                ))
            return paths
        return [] if expected == actual else [prefix]

    def _open_withholding_confirmation(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Confirm 1% Withholding"),
            "res_model": "sale.order.withholding.confirmation",
            "view_mode": "form",
            "target": "new",
            "context": {"default_sale_id": self.id},
        }

    def _confirm_withholding_decision(self, apply_withholding):
        """Confirm an issued offer or issue a safe retention-only successor."""
        self.ensure_one()
        if not _is_withholding_confirmation(self.env):
            raise AccessError(_(
                "Withholding can only be confirmed through the mandatory confirmation dialog."
            ))
        self.check_access_rights("write")
        self.check_access_rule("write")
        self._lock_revision_source()
        self.invalidate_cache(fnames=[
            "state", "active", "current_revision_id",
            "issued_offer_attachment_id", "apply_withholding",
        ])
        if (self.state != "sent" or not self.active or self.current_revision_id
                or not self.issued_offer_attachment_id):
            raise UserError(_(
                "Only the active current issued offer can be confirmed. "
                "Open the newest revision in this quotation family."
            ))
        current = bool(getattr(self, "apply_withholding", False))
        decision = "yes" if apply_withholding else "no"
        if current == apply_withholding:
            self.with_context(_lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN).write({
                "withholding_confirmation": decision,
                "withholding_confirmation_at": fields.Datetime.now(),
                "withholding_confirmation_by": self.env.user.id,
            })
            self.message_post(body=_("Customer withholding decision recorded by %(user)s: %(decision)s.") % {
                "user": self.env.user.display_name,
                "decision": _("1% withholding applies") if apply_withholding else _("1% withholding does not apply"),
            })
            return self.with_context(
                _withholding_confirmation_token=_WITHHOLDING_CONFIRMATION_TOKEN,
            ).action_confirm()

        expected_fingerprint = self._commercial_fingerprint()
        action = self.with_context(
            _retention_revision_token=_RETENTION_REVISION_TOKEN,
        ).action_view_revision_wizard(
            _("System-created retention-only revision after customer confirmation."),
        )
        revision = self.env["sale.order"].browse(action["res_id"]).exists()
        revision_fingerprint = revision._commercial_fingerprint() if revision else {}
        if not revision or revision_fingerprint != expected_fingerprint:
            difference_paths = self._fingerprint_difference_paths(
                expected_fingerprint, revision_fingerprint,
            )
            raise UserError(_(
                "The proposed revision differs from the issued commercial terms. "
                "Use the normal revision workflow and approval process. "
                "Different fields: %(fields)s."
            ) % {"fields": ", ".join(difference_paths[:8]) or _("unknown")})
        revision.with_context(
            _retention_revision_token=_RETENTION_REVISION_TOKEN,
            _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
        ).action_apply_retention_only_revision(self, expected_fingerprint, apply_withholding)
        revision.invalidate_cache()
        if revision._commercial_fingerprint() != expected_fingerprint:
            raise UserError(_(
                "Only 1% withholding may change in an automatic retention-only revision."
            ))
        revision.with_context(_lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN).write({
            "retention_only_revision": True,
            "retention_only_source_id": self.id,
            "withholding_confirmation": decision,
            "withholding_confirmation_at": fields.Datetime.now(),
            "withholding_confirmation_by": self.env.user.id,
            "sales_responsibility_accepted": self.sales_responsibility_accepted,
            "sales_responsibility_accepted_at": self.sales_responsibility_accepted_at,
            "sales_responsibility_accepted_by": self.sales_responsibility_accepted_by.id,
        })
        # Approval implementations live outside this lifecycle module.  They
        # may carry their own evidence forward only after the server-side
        # commercial fingerprint above has proved that withholding is the sole
        # change.  A normal revision never invokes this hook.
        carry_approvals = getattr(
            revision.with_context(
                _retention_revision_token=_RETENTION_REVISION_TOKEN,
            ),
            "_carry_retention_only_approvals_from",
            None,
        )
        if carry_approvals:
            carry_approvals(self)
        revision.action_issue_offer_pdf()
        revision.with_context(
            _withholding_confirmation_token=_WITHHOLDING_CONFIRMATION_TOKEN,
        ).action_confirm()
        return {"type": "ir.actions.act_window", "res_model": "sale.order",
                "res_id": revision.id, "view_mode": "form", "target": "current"}

    def _ensure_issue_authorized(self):
        self.ensure_one()
        if not (
                self.env.is_superuser()
                or self.env.user.has_group(
                    "sale_order_product_pricing.quotation_manager_group"
                )):
            self._ensure_revision_authorized()
        if self.state != "draft" or not self.active:
            raise UserError(_(
                "Only the active draft quotation can be issued. Create a new revision for changes."
            ))
        if self.issued_offer_attachment_id:
            raise UserError(_(
                "This quotation already has an issued Offer PDF and is locked."
            ))

    def action_accept_sales_responsibility(self):
        self.ensure_one()
        if self.state != "draft" or not self.active:
            raise UserError(_("Sales responsibility can be accepted only on the active draft."))
        user = self.env.user
        if not (self.env.is_superuser() or user == self.user_id or user.has_group(
                "sales_team.group_sale_manager")):
            raise AccessError(_(
                "Only the assigned Salesperson or a Sales Manager may accept responsibility."
            ))
        audit = _("Sales responsibility accepted by %(user)s.") % {
            "user": user.display_name,
        }
        self.with_context(
            _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
        ).write({
            "sales_responsibility_accepted": True,
            "sales_responsibility_accepted_at": fields.Datetime.now(),
            "sales_responsibility_accepted_by": user.id,
        })
        self.message_post(body=audit)

    def action_issue_offer_pdf(self):
        """Render the customer offer once, attach it, audit it, then lock it."""
        self.ensure_one()
        # Serialize issue so two sessions cannot attach two different
        # "official" PDFs for the same quotation version.
        self.env.cr.execute(
            "SELECT id FROM sale_order WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_cache(fnames=[
            "state", "active", "issued_offer_attachment_id",
        ])
        self._ensure_issue_authorized()
        approval_gate = getattr(
            self, "_check_quotation_issue_approval_requirements", None,
        )
        if approval_gate:
            approval_gate()
        else:
            # Compatibility only while the stabilization branch replaces the
            # former finance-control layer.  New approval code uses the hook
            # above and must not add another Sale Order state.
            finance_gate = getattr(self, "_check_finance_issue_requirements", None)
            if finance_gate:
                finance_gate()
        report_ref = "sale.action_report_saleorder"
        if not self.env.ref(report_ref, raise_if_not_found=False):
            raise UserError(_("The standard Sales Order PDF report is not available."))
        pdf, _content_type = self.env["ir.actions.report"]._render_qweb_pdf(
            report_ref, self.ids,
        )
        attachment = self.env["ir.attachment"].create({
            "name": "%s-issued-offer.pdf" % self.name,
            "type": "binary",
            "datas": base64.b64encode(pdf),
            "res_model": "sale.order",
            "res_id": self.id,
            "mimetype": "application/pdf",
        })
        issued_at = fields.Datetime.now()
        version = self.name
        audit = _(
            "Issued customer Offer PDF %(attachment)s as version %(version)s by %(user)s at %(when)s."
        ) % {
            "attachment": attachment.name,
            "version": version,
            "user": self.env.user.display_name,
            "when": issued_at,
        }
        without_sales_acceptance = not self.sales_responsibility_accepted
        exception_audit = False
        notification_partners = self.env["res.partner"]
        if without_sales_acceptance:
            exception_audit = _(
                "Issued without Sales responsibility acceptance; assigned Sales and Sales Managers were notified."
            )
            sales_managers = self.env["res.users"].sudo().search([
                ("groups_id", "in", [
                    self.env.ref("sales_team.group_sale_manager").id,
                    self.env.ref(
                        "sale_order_product_pricing.quotation_manager_group"
                    ).id,
                ]),
                ("active", "=", True),
            ])
            notification_partners = (self.user_id | sales_managers).mapped("partner_id")
            audit = "%s %s" % (audit, exception_audit)
        self.with_context(
            _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
        ).write({
            "issued_offer_attachment_id": attachment.id,
            "issued_offer_at": issued_at,
            "issued_offer_by": self.env.user.id,
            "issued_offer_version": version,
            "issued_offer_audit": audit,
            "issued_without_sales_acceptance": without_sales_acceptance,
            "state": "sent",
        })
        self.with_context(
            _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
        ).message_post(
            body=audit, attachment_ids=[attachment.id],
            partner_ids=notification_partners.ids,
        )
        return {"type": "ir.actions.act_window_close"}

    @api.model_create_multi
    def create(self, vals_list):
        internal = _is_revision_internal(self.env)
        prepared_vals = []
        for incoming in vals_list:
            vals = dict(incoming)
            if not internal:
                for field_name in _REVISION_SYSTEM_FIELDS:
                    vals.pop(field_name, None)
            prepared_vals.append(vals)

        # Nested canonical order-line creates are initial quotation setup, not
        # a later commercial edit.  The unforgeable token keeps the line guard
        # from mistaking initial create commands for a daily change.
        orders = super(
            SaleOrder,
            self.with_context(
                _lifecycle_initializing_token=_LIFECYCLE_INITIALIZING_TOKEN,
            ),
        ).create(prepared_vals)
        if not internal:
            for order in orders.filtered(lambda item: not item.unrevisioned_name):
                super(
                    SaleOrder,
                    order.with_context(_revision_internal_token=_REVISION_INTERNAL_TOKEN),
                ).write({"unrevisioned_name": order.name})
        return orders

    def write(self, vals):
        vals = dict(vals)
        lifecycle_internal = _is_lifecycle_internal(self.env)
        lifecycle_confirming = _is_lifecycle_confirming(self.env)
        revision_internal = _is_revision_internal(self.env)
        sent_orders = self.filtered(lambda order: order.state == "sent")
        if sent_orders and lifecycle_confirming:
            if (set(vals) - {"state", "date_order"}
                    or vals.get("state") != "sale"):
                raise UserError(_(
                    "Confirmation may only set the Sales Order to confirmed and set its "
                    "standard confirmation date; commercial values cannot be "
                    "changed at the same time."
                ))
        elif sent_orders and not (lifecycle_internal or revision_internal):
            raise UserError(_(
                "An issued quotation is immutable through the interface, RPC, imports, "
                "and normal reopening. Create a revision instead."
            ))
        if vals.get("state") == "sent" and not lifecycle_internal:
            raise UserError(_(
                "Use Issue Offer PDF to send and lock a quotation with its exact customer PDF."
            ))
        if (_REVISION_SYSTEM_FIELDS.intersection(vals)
                and not (revision_internal or lifecycle_internal)):
            raise AccessError(_("Revision history fields are managed by the system."))
        if "active" in vals and not _is_revision_internal(self.env):
            revision_records = self.filtered(
                lambda order: order.revision_number
                or order.current_revision_id
                or order.with_context(active_test=False).old_revision_ids
            )
            if revision_records:
                raise AccessError(_(
                    "Quotation revision history cannot be archived or restored manually."
                ))
        return super().write(vals)

    def copy(self, default=None):
        if not _is_revision_internal(self.env) and self.filtered(
                lambda order: order.state == "sent"):
            raise UserError(_(
                "A sent quotation must be copied through Create Revision so its "
                "Revision Comment and history are preserved."
            ))
        return super().copy(default)

    def action_quotation_send(self):
        if not _is_lifecycle_internal(self.env):
            raise UserError(_(
                "Use Issue Offer PDF. It stores the exact customer PDF, logs the issuer, "
                "and then locks the quotation."
            ))
        return super().action_quotation_send()

    def action_quotation_sent(self):
        if not _is_lifecycle_internal(self.env):
            raise UserError(_(
                "Use Issue Offer PDF to mark a quotation sent."
            ))
        return super().action_quotation_sent()

    def action_confirm(self):
        """Acceptance may progress an issued offer, but never edits its terms."""
        if self.filtered(
                lambda order: order.state != "sent" or not order.active
                or order.current_revision_id or not order.issued_offer_attachment_id):
            raise UserError(_(
                "Only the active current Offer PDF issued by this workflow can be "
                "confirmed. Open the newest revision or issue the quotation first."
            ))
        if not _is_withholding_confirmation(self.env):
            if len(self) != 1:
                raise UserError(_("Confirm Sales Orders one at a time so withholding can be recorded."))
            return self._open_withholding_confirmation()
        result = super(
            SaleOrder, self.with_context(
                _lifecycle_confirming_token=_LIFECYCLE_CONFIRMING_TOKEN,
                _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
            ),
        ).action_confirm()
        # A downstream double-validation module may return while leaving the
        # order in an intermediate state.  Evidence is a confirmed-SO task,
        # never a side effect of merely attempting confirmation.
        evidence_hook = getattr(self, "_create_pending_withholding_evidence", None)
        if evidence_hook and all(order.state == "sale" for order in self):
            evidence_hook()
        return result

    def action_approve(self):
        """Block obsolete two-step confirmation routes from legacy modules."""
        raise UserError(_(
            "Legacy Sales Order approval is no longer used. Confirm the current issued "
            "offer through the withholding confirmation dialog."
        ))

    def _ensure_revision_authorized(self):
        self.ensure_one()
        user = self.env.user
        if self.env.is_superuser() or user.has_group("sales_team.group_sale_manager"):
            return
        if user == self.user_id or user == self.quotation_specialist_id:
            return
        raise AccessError(_(
            "Only the assigned Salesperson, assigned Quotation Specialist, or a "
            "Sales Manager may revise this quotation."
        ))

    def _ensure_revision_source(self):
        self.ensure_one()
        self.check_access_rights("write")
        self.check_access_rule("write")
        self._ensure_revision_authorized()
        if self.state != "sent":
            raise UserError(_("Only a sent quotation can be revised."))
        if not self.active or self.current_revision_id:
            raise UserError(_(
                "Only the active, most recent quotation in a revision family can be revised."
            ))

    def _lock_revision_source(self):
        """Serialize allocation at the one current member of a family."""
        self.ensure_one()
        current = self._current_revision()
        self.env.cr.execute(
            "SELECT id FROM sale_order WHERE id = %s FOR UPDATE",
            [current.id],
        )
        current.invalidate_cache(fnames=[
            "state",
            "active",
            "current_revision_id",
            "revision_number",
            "unrevisioned_name",
        ])

    def _current_revision(self):
        """Return the current member of this revision family, including drafts.

        Old deployments may contain a chain instead of every historical record
        pointing at the newest member.  Follow that explicit chain; never infer
        a family from similarly-looking quotation names.
        """
        self.ensure_one()
        current = self.with_context(active_test=False)
        seen = set()
        while current.current_revision_id:
            if current.id in seen:
                raise UserError(_(
                    "This quotation has a circular revision link and needs administrator review."
                ))
            seen.add(current.id)
            current = current.current_revision_id.with_context(active_test=False)
        return current

    def _revision_family(self, current=None):
        """Return all explicitly linked records, including legacy chains."""
        self.ensure_one()
        current = (current or self._current_revision()).with_context(active_test=False)
        family = current
        frontier = current
        # New writes flatten every historical member to the current tip.  This
        # small traversal also makes a pre-migration legacy chain visible
        # without using display-name heuristics.
        while frontier:
            children = self.env["sale.order"].with_context(active_test=False).search([
                ("current_revision_id", "in", frontier.ids),
            ])
            children -= family
            if not children:
                break
            family |= children
            frontier = children
        return family

    @staticmethod
    def _canonical_revision_root(value, is_revision=False):
        """Return the root used for future names without changing old names.

        ``S0123-01-02`` is a malformed *revision* name and therefore has root
        ``S0123``.  A new root quotation with no revision metadata is left
        untouched even if its business sequence happens to end in ``-01``.
        """
        value = (value or "").strip()
        if not value:
            return value
        return _REVISION_SUFFIX_RE.sub("", value) if is_revision else value

    def _revision_family_root(self, family=None):
        """Return one proven canonical root or require manual family review.

        Structured family links and ``unrevisioned_name`` are evidence.  We do
        not bundle independent old quotations merely because their display
        names look similar.
        """
        self.ensure_one()
        family = family or self._revision_family()
        ambiguous = family.filtered("revision_family_ambiguous")
        if ambiguous:
            raise UserError(_(
                "This quotation revision family is marked for review. Resolve its "
                "existing family metadata before creating another revision."
            ))
        # A revision-number zero member is the strongest proof of the root.
        # Next prefer an explicitly stored root exactly as it was entered: a
        # legitimate quotation number can itself end in '-01'.
        roots = {
            (member.name or "").strip()
            for member in family if not member.revision_number
        }
        roots.discard("")
        if len(roots) > 1:
            raise UserError(_(
                "The existing revision-family metadata conflicts. It was not guessed; "
                "an administrator must resolve the family before another revision is created."
            ))
        if not roots:
            roots = {
                (member.unrevisioned_name or "").strip()
                for member in family if (member.unrevisioned_name or "").strip()
            }
        if not roots:
            # Last resort for a linked, metadata-free legacy family: only a
            # record already marked as a revision is parsed.  New root quotes
            # are never parsed from display name alone.
            roots = {
                self._canonical_revision_root(member.name, True)
                for member in family if member.revision_number
            }
        if not roots:
            roots.add((self.unrevisioned_name or self.name or "").strip())
        roots.discard("")
        if len(roots) != 1:
            raise UserError(_(
                "The existing revision-family metadata conflicts. It was not guessed; "
                "an administrator must resolve the family before another revision is created."
            ))
        return roots.pop()

    def _next_revision_number(self, family=None):
        self.ensure_one()
        family = family or self._revision_family()
        return max(family.mapped("revision_number") or [0]) + 1

    def _restore_candidates(self, current=None):
        """Previously sent family members that may be used as a draft baseline."""
        current = current or self._current_revision()
        return self._revision_family(current).filtered(
            lambda order: order.state == "sent" and order != current
        )

    @staticmethod
    def _restoration_total(order):
        currency = order.currency_id.name or ""
        return "%s %.2f" % (currency, order.amount_total)

    @staticmethod
    def _commercial_signature(order):
        line_signature = tuple(
            (
                line.display_type,
                line.product_id.id,
                line.name,
                line.product_uom_qty,
                line.product_uom.id,
                line.price_unit,
                line.discount,
                getattr(line, "discount_2", 0.0),
                getattr(line, "discount_3", 0.0),
                tuple(sorted(line.tax_id.ids)),
            )
            for line in order.order_line
        )
        incoterm = (
            getattr(order, "incoterm_id", False)
            or getattr(order, "incoterm", False)
        )
        return (
            order.partner_id.id,
            order.partner_invoice_id.id,
            order.partner_shipping_id.id,
            order.currency_id.id,
            order.pricelist_id.id,
            order.payment_term_id.id,
            order.fiscal_position_id.id,
            incoterm.id if incoterm else False,
            order.client_order_ref,
            order.note,
            getattr(order, "ks_enable_discount", False),
            getattr(order, "ks_global_discount_type", False),
            getattr(order, "ks_global_discount_rate", 0.0),
            line_signature,
        )

    def _restoration_difference_summary(self, current, restored_source, reason):
        """Record a truthful commercial comparison without pricing internals."""
        current.ensure_one()
        restored_source.ensure_one()
        same_snapshot = (
            self._commercial_signature(current)
            == self._commercial_signature(restored_source)
        )
        difference = _(
            "Customer-commercial snapshots match."
        ) if same_snapshot else _(
            "Customer-commercial snapshots differ."
        )
        return _(
            "Restored %(source)s into new draft from current %(current)s. "
            "Current: %(current_lines)s lines, %(current_total)s. "
            "Restored source: %(source_lines)s lines, %(source_total)s. "
            "%(difference)s Reason: %(reason)s"
        ) % {
            "source": restored_source.name,
            "current": current.name,
            "current_lines": len(current.order_line),
            "current_total": self._restoration_total(current),
            "source_lines": len(restored_source.order_line),
            "source_total": self._restoration_total(restored_source),
            "difference": difference,
            "reason": reason,
        }

    def _copy_restored_draft(self, restored_source, defaults, internal_context):
        """Copy the exact commercial/pricing snapshot but use fresh quote dates.

        copy_data retains protected pricing values under the existing in-process
        pricing token. Removing quote lifecycle dates lets Odoo's normal defaults
        establish the new proposal date and validity.
        """
        values = restored_source.sudo().with_context(**internal_context).copy_data(
            default=defaults
        )[0]
        for field_name in ("date_order", "validity_date"):
            values.pop(field_name, None)
        return self.env["sale.order"].sudo().with_context(**internal_context).create(values)

    def action_revision(self):
        self.ensure_one()
        self._ensure_revision_source()
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Quotation Revision"),
            "res_model": "revision.reason",
            "view_mode": "form",
            "target": "new",
            "context": {"default_sale_id": self.id},
        }

    def action_restore_historical_revision(self):
        """Open the controlled restore wizard for this quotation family."""
        self.ensure_one()
        current = self._current_revision()
        current.check_access_rights("write")
        current.check_access_rule("write")
        current._ensure_revision_authorized()
        candidates = self._restore_candidates(current)
        if not candidates:
            raise UserError(_(
                "This revision family has no earlier sent quotation that can be restored."
            ))
        return {
            "type": "ir.actions.act_window",
            "name": _("Restore Historical Offer"),
            "res_model": "revision.reason",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_sale_id": self.id,
                "default_expected_current_revision_id": current.id,
                "default_is_restoration": True,
            },
        }

    def action_restore_revision(self, restored_source, reason, expected_current_id=False):
        """Restore a sent family member as a new N+1 draft.

        Historical sent quotations remain immutable. Even when an editable
        current draft already exists, it is archived as superseded history and
        a new draft receives the restored snapshot.
        """
        self.ensure_one()
        comment = (reason or "").strip()
        if not comment:
            raise UserError(_("A Restoration Reason is required."))
        if not expected_current_id:
            raise UserError(_(
                "This restoration dialog is stale or incomplete. Reopen it and try again."
            ))

        restored_source = self.env["sale.order"].with_context(active_test=False).browse(
            restored_source.id if hasattr(restored_source, "id") else restored_source
        )
        if not restored_source.exists():
            raise UserError(_("Select a previously sent quotation to restore."))
        restored_source.check_access_rights("read")
        restored_source.check_access_rule("read")

        current = self._current_revision()
        current.check_access_rights("write")
        current.check_access_rule("write")
        current._ensure_revision_authorized()
        if expected_current_id and current.id != expected_current_id:
            raise UserError(_(
                "This revision family changed while the restore dialog was open. Reopen it and try again."
            ))

        # Serialize against ordinary revision creation and other restore
        # requests. Re-resolving after the lock rejects stale wizards.
        current._lock_revision_source()
        self.invalidate_cache(fnames=["current_revision_id"])
        current = self._current_revision()
        if expected_current_id and current.id != expected_current_id:
            raise UserError(_(
                "This revision family changed while the restore dialog was open. Reopen it and try again."
            ))
        current.check_access_rights("write")
        current.check_access_rule("write")
        current._ensure_revision_authorized()

        candidates = self._restore_candidates(current)
        if restored_source not in candidates:
            raise UserError(_(
                "Only an earlier sent quotation in the same revision family can be restored."
            ))

        family = self._revision_family(current)
        family_name = current._revision_family_root(family)
        next_number = current._next_revision_number(family)
        now = fields.Datetime.now()
        internal_context = {
            "_revision_internal_token": _REVISION_INTERNAL_TOKEN,
            "_pricing_internal_token": _PRICING_INTERNAL_TOKEN,
        }
        summary = self._restoration_difference_summary(
            current, restored_source, comment,
        )
        revision = self._copy_restored_draft(restored_source, {
            "name": "%s-%02d" % (family_name, next_number),
            "state": "draft",
            "active": True,
            "current_revision_id": False,
            "revision_number": next_number,
            "unrevisioned_name": family_name,
            "revision_reason": False,
            "revision_date": False,
            "revision_author_id": False,
            "restored_from_revision_id": restored_source.id,
            "restoration_reason": comment,
            "restoration_date": now,
            "restoration_author_id": self.env.user.id,
            "restoration_difference_summary": summary,
        }, internal_context)

        superseded_comment = _(
            "Superseded by restoration from %(source)s. %(reason)s"
        ) % {"source": restored_source.name, "reason": comment}
        # Only system-owned family metadata changes on the old current record;
        # its commercial snapshot remains untouched whether sent or draft.
        current.sudo().with_context(**internal_context).write({
            "active": False,
            "current_revision_id": revision.id,
            "revision_reason": superseded_comment,
            "revision_date": now,
            "revision_author_id": self.env.user.id,
        })
        historical = family - current
        if historical:
            historical.sudo().with_context(**internal_context).write({
                "current_revision_id": revision.id,
            })

        return {
            "type": "ir.actions.act_window",
            "name": _("Restored Quotation Revision"),
            "res_model": "sale.order",
            "res_id": revision.id,
            "view_mode": "form",
            "view_id": self.env.ref("sale.view_order_form").id,
            "target": "current",
        }

    def action_view_revision_wizard(self, reason):
        """Create a draft successor while preserving the sent source exactly."""
        self.ensure_one()
        self._ensure_revision_source()
        comment = (reason or "").strip()
        if not comment:
            raise UserError(_("A Revision Comment is required."))

        # The wizard-open check above gives immediate feedback.  Confirmation
        # then locks and rechecks the row so simultaneous requests cannot both
        # allocate the same revision number or leave an orphan successor.
        self._lock_revision_source()
        self._ensure_revision_source()

        source = self
        family = source._revision_family(source)
        family_name = source._revision_family_root(family)
        next_number = source._next_revision_number(family)
        historical = family - source
        retention_only = (
            self.env.context.get("_retention_revision_token")
            is _RETENTION_REVISION_TOKEN
        )
        internal_context = {
            "_revision_internal_token": _REVISION_INTERNAL_TOKEN,
            "_pricing_internal_token": _PRICING_INTERNAL_TOKEN,
        }
        if retention_only:
            internal_context["_retention_revision_token"] = _RETENTION_REVISION_TOKEN
            internal_context["_retention_date_copy_token"] = _RETENTION_DATE_COPY_TOKEN
        copy_defaults = {
            "name": "%s-%02d" % (family_name, next_number),
            "state": "draft",
            "active": True,
            "current_revision_id": False,
            "revision_number": next_number,
            "unrevisioned_name": family_name,
            "revision_reason": False,
            "revision_date": False,
            "revision_author_id": False,
        }
        if retention_only:
            # A retention-only successor must retain the issued commercial
            # snapshot exactly.  The date module normally assigns a new draft
            # today's Offer Date, and standard Sale may default date_order;
            # either value can change expiry/rate evidence before the
            # withholding-only comparison runs.
            copy_defaults.update({
                "date_order": source.date_order,
                "offer_date": source.offer_date,
                "validity_date": source.validity_date,
                "offer_expiry_days": source.offer_expiry_days,
                "commitment_date": source.commitment_date,
            })
        # The exact clone includes pricing and specialist fields that ordinary
        # assigned Salespeople cannot read/write directly because of field
        # groups.  Authorization is complete above; sudo is scoped to this
        # mechanical copy and keeps the initiating user's uid for attribution.
        revision = source.sudo().with_context(**internal_context).copy(
            default=copy_defaults,
        )

        # Authorization was checked against the source above.  Sudo is limited
        # to system-owned family metadata, including relinking inactive history
        # that normal record rules deliberately hide.
        source.sudo().with_context(**internal_context).write({
            "active": False,
            "current_revision_id": revision.id,
            "revision_reason": comment,
            "revision_date": fields.Datetime.now(),
            "revision_author_id": self.env.user.id,
        })
        if historical:
            historical.sudo().with_context(**internal_context).write({
                "current_revision_id": revision.id,
            })

        return {
            "type": "ir.actions.act_window",
            "name": _("Quotation Revision"),
            "res_model": "sale.order",
            "res_id": revision.id,
            "view_mode": "form",
            "view_id": self.env.ref("sale.view_order_form").id,
            "target": "current",
        }

    def action_open_revision_history(self):
        self.ensure_one()
        current = self.current_revision_id or self
        family = current.with_context(active_test=False).old_revision_ids | current
        search_view = self.env.ref(
            "sale_revision_history.sale_order_revision_history_search"
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Revision History - %s") % (current.unrevisioned_name or current.name),
            "res_model": "sale.order",
            "view_mode": "tree,form",
            "views": [
                (self.env.ref("sale_revision_history.sale_order_revision_history_tree").id, "tree"),
                (self.env.ref("sale.view_order_form").id, "form"),
            ],
            # Dynamic client actions expect the same [id, name] shape returned
            # by ir.actions.act_window.read(); a bare integer is ignored and
            # silently falls back to the standard Sales search view.
            "search_view_id": [search_view.id, search_view.name],
            # A family-only history includes its current draft and every
            # historical version, newest first.  No unrelated quotation can
            # leak in through the generic Sales search view.
            "domain": [("id", "in", family.ids)],
            "context": {
                "active_test": False,
            },
        }


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    is_add_below_placeholder = fields.Boolean(
        string="Add Below Placeholder",
        default=False,
        copy=False,
        readonly=True,
        help="System-managed marker for a newly inserted blank Add Below row.",
    )

    _sql_constraints = [
        (
            "accountable_required_fields",
            "CHECK(display_type IS NOT NULL OR is_add_below_placeholder OR "
            "(product_id IS NOT NULL AND product_uom IS NOT NULL))",
            "Missing required fields on accountable sale order line.",
        ),
    ]

    def _ensure_lifecycle_line_editable(self):
        orders = self.mapped("order_id")
        if orders.filtered(lambda order: order.state == "sent"):
            raise UserError(_(
                "Lines on an issued quotation are immutable through the interface, "
                "RPC, imports, and normal reopening. Create a revision instead."
            ))

    def action_add_below(self):
        """Retired until row insertion can preserve the active-line position."""
        raise UserError(_(
            "Add Below is temporarily disabled. Use Add a product, which keeps the quotation in place."
        ))

    def write(self, vals):
        if "is_add_below_placeholder" in vals and not _is_lifecycle_internal(self.env):
            raise AccessError(_("Add Below placeholder evidence is system-managed."))
        if self.mapped("order_id").filtered(lambda order: order.state == "sent") and not _is_lifecycle_internal(self.env):
            raise UserError(_(
                "Lines on an issued quotation are immutable through the interface, "
                "RPC, imports, and normal reopening. Create a revision instead."
            ))
        result = super().write(vals)
        completed = self.filtered(
            lambda line: line.is_add_below_placeholder
            and line.product_id and line.product_uom
        )
        if completed:
            completed.with_context(
                _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
            ).write({"is_add_below_placeholder": False})
        return result

    @api.model_create_multi
    def create(self, vals_list):
        if any(values.get("is_add_below_placeholder") for values in vals_list) and not _is_lifecycle_internal(self.env):
            raise AccessError(_("Add Below placeholder evidence is system-managed."))
        if not (
                _is_lifecycle_initializing(self.env)
                or _is_pricing_internal(self.env)
                or _is_finance_internal(self.env)
                or _is_pricing_downpayment(self.env)):
            order_ids = [values.get("order_id") for values in vals_list if values.get("order_id")]
            orders = self.env["sale.order"].browse(order_ids)
            if orders.filtered(lambda order: order.state == "sent"):
                raise UserError(_(
                    "Quotation lines cannot be added after Issue Offer PDF. Create a revision instead."
                ))
        return super().create(vals_list)

    def unlink(self):
        if self.mapped("order_id").filtered(lambda order: order.state == "sent") and not _is_lifecycle_internal(self.env):
            raise UserError(_(
                "Lines on an issued quotation are immutable through the interface, "
                "RPC, imports, and normal reopening. Create a revision instead."
            ))
        return super().unlink()


class SaleOrderOption(models.Model):
    _inherit = "sale.order.option"

    @api.model_create_multi
    def create(self, vals_list):
        order_ids = [vals.get("order_id") for vals in vals_list if vals.get("order_id")]
        orders = self.env["sale.order"].browse(order_ids)
        if orders.filtered(lambda order: order.state == "sent"):
            raise UserError(_(
                "Issued quotation optional products are immutable. Create a revision instead."
            ))
        return super().create(vals_list)

    def write(self, vals):
        if self.mapped("order_id").filtered(lambda order: order.state == "sent"):
            raise UserError(_("Issued quotation optional products are immutable. Create a revision instead."))
        return super().write(vals)

    def unlink(self):
        if self.mapped("order_id").filtered(lambda order: order.state == "sent"):
            raise UserError(_("Issued quotation optional products are immutable. Create a revision instead."))
        return super().unlink()
