# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    state = fields.Selection([
        ('draft', 'Quotation'),
        ('approve', 'Approved'),
        ('sent', 'Quotation Sent'),
        ('sale', 'Sales Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, index=True, tracking=3, default='draft')

    # Incomplete validation of the approved state
    def action_to_approve(self):
        self.state = 'approve'


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    margin = fields.Float(
        "Margin", compute='_compute_margin',
        digits='Product Price', store=True, groups="egy-trade_custom.group_product_logistics")
    margin_percent = fields.Float(
        "Margin (%)", compute='_compute_margin', store=True, groups="egy-trade_custom.group_product_logistics")
    purchase_price = fields.Float(
        string='Cost', compute="_compute_purchase_price",
        digits='Product Price', store=True, readonly=False,
        groups="egy-trade_custom.group_product_logistics")