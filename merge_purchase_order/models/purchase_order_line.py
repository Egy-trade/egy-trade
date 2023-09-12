# -*- coding:utf-8 -*-
from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # Purchase order origin when spliting purchase order
    purchase_origin = fields.Char(string='Purchase Origin')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
