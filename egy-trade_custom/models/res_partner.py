# -*- coding: utf-8 -*-

from odoo import models, fields


class SupplierInfo(models.Model):
    _inherit = 'res.partner'

    delay = fields.Integer(string='Delivery Lead Time', default=1)
