# -*- coding: utf-8 -*-

from odoo import fields, models


class RevisionReason(models.TransientModel):
    _name = "revision.reason"
    _rec_name = "name"
    _description = "Quotation Revision Comment"

    name = fields.Text(string="Revision Comment", required=True)
    sale_id = fields.Many2one(
        "sale.order", string="Quotation", required=True, readonly=True,
    )

    def action_confirm(self):
        self.ensure_one()
        return self.sale_id.action_view_revision_wizard(self.name)
