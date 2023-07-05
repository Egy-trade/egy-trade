from odoo import models, fields


class ProductAnalysis(models.Model):
    _name = 'product.analysis'
    _description = 'Product Analysis'

    product_id = fields.Many2one('product.product', string='Product')
    sale_id = fields.Many2one('sale.order', string='SO')
    state = fields.Selection(related='sale_id.state', store=True)
    sale_order_date = fields.Datetime(related='sale_id.date_order', store=True)
    quantity = fields.Float(default=1)
    purchase_price_estimate = fields.Float(string='Purchase Price')
    factor = fields.Float(default=1)
    currency_rate_estimate = fields.Float(string='Currency Rate')
    note = fields.Char()
