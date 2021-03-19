# -*- coding: utf-8 -*-

from odoo import models, fields


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    shipment_state = fields.Selection([
        ('waiting', 'Waiting'),
        ('shipped', 'Shipped'),
        ('customs', 'Customs'),
    ], string='Shipment Status', tracking=True, default='waiting', required=True)
