# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class inherit_sale(models.Model):
    _inherit = "sale.order"

    # state = fields.Selection(selection_add=[('waiting_approve', 'Waiting Approve')])

    def action_approve(self):
        self.write({'state': 'draft'})






