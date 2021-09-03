# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


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


    product_vendor = fields.Many2one(related='product_id.vendor_id')
    product_family_name = fields.Many2one(related='product_id.family_name')
    product_color = fields.Many2one(related='product_id.color')
    product_type_spec = fields.Char(related='product_id.product_type_spec')
    product_cct = fields.Char(related='product_id.cct')
    product_driver = fields.Char(related='product_id.driver_manufacture')
    product_power = fields.Char(related='product_id.power')
    product_ip = fields.Char(related='product_id.ip')
    product_led_voltage = fields.Char(related='product_id.led_voltage')
    product_lumen = fields.Char(related='product_id.lumen')



    @api.constrains('discount')
    def _check_discount(self):
        if self.discount > self.env.user.max_discount:
            raise ValidationError(_(f'Your maximum allowed discount per order line is {self.env.user.max_discount}'))