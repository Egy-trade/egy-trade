# -*- coding: utf-8 -*-
"""Explicit decision before the first commercial change of a Cairo day."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class QuotationCommercialChange(models.TransientModel):
    _name = "quotation.commercial.change"
    _description = "Quotation Commercial Change Decision"

    sale_id = fields.Many2one("sale.order", required=True, readonly=True)
    decision = fields.Selection(
        [("update_today", "Update Today"), ("create_revision", "Create Revision")],
        required=True, default="update_today",
        help="Update Today retains this unsent draft; Create Revision keeps it as history and opens a new draft.",
    )
    reason = fields.Text(
        string="Revision Comment",
        help="Required when a new revision is created; explains the commercial change.",
    )
    must_create_revision = fields.Boolean(
        compute="_compute_must_create_revision", readonly=True,
    )

    @api.depends("sale_id.state", "sale_id.issued_offer_attachment_id")
    def _compute_must_create_revision(self):
        for wizard in self:
            wizard.must_create_revision = bool(
                wizard.sale_id.state == "sent" or wizard.sale_id.issued_offer_attachment_id
            )

    @api.onchange("must_create_revision")
    def _onchange_must_create_revision(self):
        if self.must_create_revision:
            self.decision = "create_revision"

    def action_confirm(self):
        self.ensure_one()
        order = self.sale_id
        if not order:
            raise UserError(_("Select a quotation first."))
        if self.must_create_revision and self.decision != "create_revision":
            raise UserError(_(
                "An issued quotation cannot be updated today. Create a revision instead."
            ))
        if self.decision == "update_today":
            order._ensure_revision_authorized()
            if order.state != "draft" or not order.active:
                raise UserError(_("Only an active unsent draft can be updated today."))
            order._record_commercial_change("update_today", self.reason)
            return {"type": "ir.actions.act_window_close"}
        if not (self.reason or "").strip():
            raise UserError(_("A Revision Comment is required when creating a revision."))
        if order.state == "sent":
            return order.action_view_revision_wizard(self.reason)
        return order.action_create_draft_revision(self.reason)
