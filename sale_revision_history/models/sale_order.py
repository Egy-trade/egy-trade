# -*- coding: utf-8 -*-
"""Safe, auditable quotation revisions.

A revision never reopens or mutates the quotation that was sent.  It creates a
new draft and keeps every superseded quotation as an inactive historical
record in the same revision family.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.sale_order_product_pricing.models.sale_order import (
    _PRICING_INTERNAL_TOKEN,
)


_REVISION_INTERNAL_TOKEN = object()
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

        # Ordinary quotations do not need revision-family metadata until the
        # first revision is created.  Avoiding a second write here keeps the
        # standard batched sale-order create path intact and inexpensive.
        return super().create(prepared_vals)

    def write(self, vals):
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
        return super().write(vals)

    def copy(self, default=None):
        if not _is_revision_internal(self.env) and self.filtered(
                lambda order: order.state == "sent"):
            raise UserError(_(
                "A sent quotation must be copied through Create Revision so its "
                "Revision Comment and history are preserved."
            ))
        return super().copy(default)

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
            "unrevisioned_name": family_name,
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
            "unrevisioned_name": family_name,
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
            # This action is the comment history, not another quotation list.
            # Keep the current blank draft out even if the web client ignores
            # a search-default hint while opening a dynamic action.
            "domain": [
                ("id", "in", family.ids),
                ("revision_reason", "!=", False),
            ],
            "context": {
                "active_test": False,
                "search_default_has_revision_comment": 1,
            },
        }
