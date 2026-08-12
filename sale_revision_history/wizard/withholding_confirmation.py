# -*- coding: utf-8 -*-
"""Mandatory, auditable withholding decision before Sales Order confirmation."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrderWithholdingConfirmation(models.TransientModel):
    _name = "sale.order.withholding.confirmation"
    _description = "Sales Order Withholding Confirmation"

    sale_id = fields.Many2one("sale.order", required=True, readonly=True)
    decision = fields.Selection(
        [("yes", "Yes - 1% withholding applies"),
         ("no", "No - 1% withholding does not apply")],
        required=True,
        string="Customer confirmation",
        help="Ask the customer or Finance whether 1% withholding applies and whether "
             "supporting withholding evidence will be provided.",
    )
    issued_withholding = fields.Boolean(
        related="sale_id.apply_withholding", readonly=True,
        string="Issued offer includes 1% withholding",
    )

    @api.onchange("sale_id")
    def _onchange_sale_id(self):
        if self.sale_id and self.sale_id.state != "sent":
            self.sale_id = False

    def action_confirm(self):
        self.ensure_one()
        if not self.sale_id or self.sale_id.state != "sent":
            raise UserError(_("The issued quotation is no longer available for confirmation."))
        if self.decision not in ("yes", "no"):
            raise UserError(_("State whether 1% withholding applies before confirming."))
        from odoo.addons.sale_revision_history.models.sale_order import (
            _WITHHOLDING_CONFIRMATION_TOKEN,
        )
        return self.sale_id.with_context(
            _withholding_confirmation_token=_WITHHOLDING_CONFIRMATION_TOKEN,
        )._confirm_withholding_decision(self.decision == "yes")
