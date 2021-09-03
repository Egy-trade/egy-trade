# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order'

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        self.order_line = False


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    product_vendor = fields.Many2one(related='product_id.vendor_id')
    product_family_name = fields.Many2one(related='product_id.family_name')
    product_power = fields.Char(related='product_id.power')
    product_ip = fields.Char(related='product_id.ip')
    product_lumen = fields.Char(related='product_id.lumen')
