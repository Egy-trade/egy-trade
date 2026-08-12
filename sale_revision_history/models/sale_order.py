# -*- coding: utf-8 -*-
"""Safe, auditable quotation revisions.

A revision never reopens or mutates the quotation that was sent.  It creates a
new draft and keeps every superseded quotation as an inactive historical
record in the same revision family.
"""

import base64
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.sale_order_product_pricing.models.sale_order import (
    _PRICING_INTERNAL_TOKEN,
    _is_pricing_downpayment,
    _is_pricing_internal,
)
from odoo.addons.sale_order_product_pricing.models.finance_controls import (
    _is_finance_internal,
)


_REVISION_INTERNAL_TOKEN = object()
_LIFECYCLE_INTERNAL_TOKEN = object()
_LIFECYCLE_INITIALIZING_TOKEN = object()
_LIFECYCLE_CONFIRMING_TOKEN = object()
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
}


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


_COMMERCIAL_ORDER_FIELDS = {
    "partner_id", "partner_invoice_id", "partner_shipping_id", "pricelist_id",
    "currency_id", "payment_term_id", "fiscal_position_id", "incoterm",
    "incoterm_id", "client_order_ref", "note", "user_id",
    "quotation_specialist_id", "sale_order_template_id", "sale_order_option_ids",
    "warehouse_id", "commitment_date", "offer_expiry_days",
    "order_line", "tax_treatment", "ks_enable_discount", "ks_global_discount_type",
    "ks_global_discount_rate",
}
_COMMERCIAL_LINE_FIELDS = {
    "sn", "sequence", "display_type", "product_id", "name", "product_uom_qty",
    "product_uom", "price_unit", "discount", "discount_2", "discount_3",
    "tax_id", "purchase_price_estimate", "factor", "line_factor",
}


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
        help="Cairo business date on which the commercial-change decision was last recorded.",
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

    def _cairo_today(self):
        self.ensure_one()
        return fields.Date.context_today(self.with_context(tz="Africa/Cairo"))

    def _ensure_daily_commercial_change_decided(self):
        pending = self.filtered(
            lambda order: order.state == "draft" and order.active
            and order.commercial_change_date != order._cairo_today()
        )
        if pending:
            raise UserError(_(
                "Record Update Today or Create Revision before saving the first "
                "commercial change for this quotation in the Cairo business day."
            ))

    def action_record_commercial_change(self):
        self.ensure_one()
        if self.state != "draft" or not self.active:
            raise UserError(_(
                "A non-current quotation is immutable. Create a revision instead."
            ))
        return {
            "type": "ir.actions.act_window",
            "name": _("Record Commercial Change"),
            "res_model": "quotation.commercial.change",
            "view_mode": "form",
            "target": "new",
            "context": {"default_sale_id": self.id},
        }

    def _record_commercial_change(self, decision, reason=False):
        """Audit the daily decision without touching Odoo's ``date_order``."""
        self.ensure_one()
        self.check_access_rights("write")
        self.check_access_rule("write")
        self._ensure_revision_authorized()
        if self.state != "draft" or not self.active:
            raise UserError(_(
                "Only the active unsent draft can record Update Today. Create a revision instead."
            ))
        today = self._cairo_today()
        if decision != "update_today":
            raise UserError(_("Only Update Today can be recorded on this quotation."))
        audit = _(
            "%(decision)s recorded by %(user)s on %(date)s Cairo business day."
        ) % {
            "decision": "Update Today",
            "user": self.env.user.display_name,
            "date": today,
        }
        if reason:
            audit = "%s %s" % (audit, reason.strip())
        self.with_context(
            _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
        ).write({
            "offer_date": today,
            "validity_date": today + timedelta(days=self.offer_expiry_days),
            "commercial_change_date": today,
            "commercial_change_decision": decision,
            "commercial_change_decision_at": fields.Datetime.now(),
            "commercial_change_decision_by": self.env.user.id,
            "commercial_change_audit": audit,
        })
        self.message_post(body=audit)

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
            if set(vals) - {"state", "date_order"} or vals.get("state") != "sale":
                raise UserError(_(
                    "Confirmation may only set the Sales Order state and standard confirmation "
                    "date; commercial values cannot be changed at the same time."
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
        needs_daily_decision = bool(
            _COMMERCIAL_ORDER_FIELDS.intersection(vals)
            and not lifecycle_internal
            and not revision_internal
            and not _is_pricing_internal(self.env)
        )
        if _REVISION_SYSTEM_FIELDS.intersection(vals) and not _is_revision_internal(self.env):
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
        result = super().write(vals)
        # Run after lower-layer ACL/role validation so unauthorized users see
        # the real access error rather than a generic daily-decision message.
        # Raising here rolls the complete transaction back, including nested
        # one2many commands, so an undecided commercial save never persists.
        if needs_daily_decision:
            self._ensure_daily_commercial_change_decided()
        return result

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
                lambda order: order.state != "sent" or not order.issued_offer_attachment_id):
            raise UserError(_(
                "Only an Offer PDF issued by this workflow can be confirmed. "
                "Issue the quotation first."
            ))
        return super(
            SaleOrder, self.with_context(
                _lifecycle_confirming_token=_LIFECYCLE_CONFIRMING_TOKEN,
                _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
            ),
        ).action_confirm()

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
        """Serialize revision numbering and successor creation for one quote."""
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id FROM sale_order WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_cache(fnames=[
            "state",
            "active",
            "current_revision_id",
            "revision_number",
            "unrevisioned_name",
        ])

    def _current_revision(self):
        """Return the current member of this revision family, including drafts."""
        self.ensure_one()
        return self.current_revision_id or self

    def _revision_family(self, current=None):
        """Return all records in the family, including archived history."""
        self.ensure_one()
        current = current or self._current_revision()
        return current.with_context(active_test=False).old_revision_ids | current

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

    def action_create_draft_revision(self, reason):
        """Create a successor from the active draft after a daily decision.

        The old draft becomes inactive history; it is never overwritten.  This
        is distinct from the established sent-offer revision flow below.
        """
        self.ensure_one()
        comment = (reason or "").strip()
        if not comment:
            raise UserError(_("A Revision Comment is required."))
        self.check_access_rights("write")
        self.check_access_rule("write")
        self._ensure_revision_authorized()
        if self.state != "draft" or not self.active or self.current_revision_id:
            raise UserError(_(
                "Only the active current draft can be revised from a commercial-change decision."
            ))
        self._lock_revision_source()
        self.invalidate_cache(fnames=["state", "active", "current_revision_id"])
        if self.state != "draft" or not self.active or self.current_revision_id:
            raise UserError(_(
                "This quotation changed while the decision dialog was open. Reopen it and try again."
            ))
        family = self._revision_family(self)
        next_number = max(family.mapped("revision_number")) + 1
        family_name = self.unrevisioned_name or self.name
        now = fields.Datetime.now()
        internal_context = {
            "_revision_internal_token": _REVISION_INTERNAL_TOKEN,
            "_pricing_internal_token": _PRICING_INTERNAL_TOKEN,
            "_lifecycle_internal_token": _LIFECYCLE_INTERNAL_TOKEN,
        }
        revision = self.sudo().with_context(**internal_context).copy(default={
            "name": "%s-%02d" % (family_name, next_number),
            "state": "draft",
            "active": True,
            "current_revision_id": False,
            "revision_number": next_number,
            "unrevisioned_name": family_name,
            "revision_reason": False,
            "revision_date": False,
            "revision_author_id": False,
            "commercial_change_date": self._cairo_today(),
            "commercial_change_decision": "create_revision",
            "commercial_change_decision_at": now,
            "commercial_change_decision_by": self.env.user.id,
            "commercial_change_audit": _(
                "Create Revision recorded by %(user)s on %(date)s Cairo business day. %(reason)s"
            ) % {
                "user": self.env.user.display_name,
                "date": self._cairo_today(),
                "reason": comment,
            },
        })
        self.sudo().with_context(**internal_context).write({
            "active": False,
            "current_revision_id": revision.id,
            "revision_reason": comment,
            "revision_date": now,
            "revision_author_id": self.env.user.id,
        })
        historical = family - self
        if historical:
            historical.sudo().with_context(**internal_context).write({
                "current_revision_id": revision.id,
            })
        revision.message_post(body=revision.commercial_change_audit)
        return {
            "type": "ir.actions.act_window",
            "name": _("Quotation Revision"),
            "res_model": "sale.order",
            "res_id": revision.id,
            "view_mode": "form",
            "view_id": self.env.ref("sale.view_order_form").id,
            "target": "current",
        }


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
        next_number = max(family.mapped("revision_number")) + 1
        family_name = current.unrevisioned_name or current.name
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
        family_name = source.unrevisioned_name or source.name
        next_number = source.revision_number + 1
        historical = source.with_context(active_test=False).old_revision_ids
        internal_context = {
            "_revision_internal_token": _REVISION_INTERNAL_TOKEN,
            "_pricing_internal_token": _PRICING_INTERNAL_TOKEN,
        }
        # The exact clone includes pricing and specialist fields that ordinary
        # assigned Salespeople cannot read/write directly because of field
        # groups.  Authorization is complete above; sudo is scoped to this
        # mechanical copy and keeps the initiating user's uid for attribution.
        revision = source.sudo().with_context(**internal_context).copy(default={
            "name": "%s-%02d" % (family_name, next_number),
            "state": "draft",
            "active": True,
            "current_revision_id": False,
            "revision_number": next_number,
            "unrevisioned_name": family_name,
            "revision_reason": False,
            "revision_date": False,
            "revision_author_id": False,
        })

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
        orders._ensure_daily_commercial_change_decided()

    def action_add_below(self):
        """Add one blank product row directly after this commercial line."""
        self.ensure_one()
        order = self.order_id
        order.check_access_rights("write")
        order.check_access_rule("write")
        if order.state != "draft" or not order.active:
            raise UserError(_("Add Below is available only on the active draft quotation."))
        if self.display_type or not self.product_id:
            raise UserError(_("Add Below is available only on a product line."))
        if order.commercial_change_date != order._cairo_today():
            # A row button can return a wizard action, unlike an x2many write.
            # After recording the decision, the user clicks Add Below again.
            return order.action_record_commercial_change()
        following = order.order_line.filtered(
            lambda line: line.id != self.id and line.sequence > self.sequence
        )
        for line in following.sorted("sequence", reverse=True):
            line.with_context(
                _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
            ).write({"sequence": line.sequence + 1})
        # Intentionally pass no source commercial values.  The pricing module
        # supplies only the header Global Factor; product, quantity, prices,
        # estimates, discounts, Item #, and Line Factor start blank/default.
        new_line = self.env["sale.order.line"].with_context(
            _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
        ).create({
            "order_id": order.id,
            "sequence": self.sequence + 1,
            "name": _("New product line"),
            "product_uom_qty": 0.0,
            "is_add_below_placeholder": True,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
            "context": {"focus_line_id": new_line.id},
        }

    def write(self, vals):
        if "is_add_below_placeholder" in vals and not _is_lifecycle_internal(self.env):
            raise AccessError(_("Add Below placeholder evidence is system-managed."))
        if self.mapped("order_id").filtered(lambda order: order.state == "sent") and not _is_lifecycle_internal(self.env):
            raise UserError(_(
                "Lines on an issued quotation are immutable through the interface, "
                "RPC, imports, and normal reopening. Create a revision instead."
            ))
        if (
                _COMMERCIAL_LINE_FIELDS.intersection(vals)
                and not (
                    _is_lifecycle_internal(self.env)
                    or _is_pricing_internal(self.env)
                    or _is_finance_internal(self.env))):
            self.mapped("order_id")._ensure_daily_commercial_change_decided()
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
            orders._ensure_daily_commercial_change_decided()
        return super().create(vals_list)

    def unlink(self):
        if self.mapped("order_id").filtered(lambda order: order.state == "sent") and not _is_lifecycle_internal(self.env):
            raise UserError(_(
                "Lines on an issued quotation are immutable through the interface, "
                "RPC, imports, and normal reopening. Create a revision instead."
            ))
        if not (
                _is_lifecycle_internal(self.env)
                or _is_pricing_internal(self.env)
                or _is_finance_internal(self.env)):
            self.mapped("order_id")._ensure_daily_commercial_change_decided()
        return super().unlink()


class SaleOrderOption(models.Model):
    _inherit = "sale.order.option"

    def write(self, vals):
        if self.mapped("order_id").filtered(lambda order: order.state == "sent"):
            raise UserError(_("Issued quotation optional products are immutable. Create a revision instead."))
        return super().write(vals)

    def unlink(self):
        if self.mapped("order_id").filtered(lambda order: order.state == "sent"):
            raise UserError(_("Issued quotation optional products are immutable. Create a revision instead."))
        return super().unlink()
