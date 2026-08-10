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
    )
    revision_date = fields.Datetime(
        string="Revised On", readonly=True, copy=False, index=True,
    )
    revision_author_id = fields.Many2one(
        "res.users", string="Revised By", readonly=True, copy=False, index=True,
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

        orders = super().create(prepared_vals)
        if not internal:
            for order in orders.filtered(lambda item: not item.unrevisioned_name):
                super(
                    SaleOrder,
                    order.with_context(_revision_internal_token=_REVISION_INTERNAL_TOKEN),
                ).write({"unrevisioned_name": order.name})
        return orders

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
        return {
            "type": "ir.actions.act_window",
            "name": _("Revision History - %s") % (current.unrevisioned_name or current.name),
            "res_model": "sale.order",
            "view_mode": "tree,form",
            "views": [
                (self.env.ref("sale_revision_history.sale_order_revision_history_tree").id, "tree"),
                (self.env.ref("sale.view_order_form").id, "form"),
            ],
            "search_view_id": self.env.ref(
                "sale_revision_history.sale_order_revision_history_search"
            ).id,
            "domain": [("id", "in", family.ids)],
            "context": {
                "active_test": False,
                "search_default_has_revision_comment": 1,
            },
        }
