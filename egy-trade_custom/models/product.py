# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date
import pandas as pd


class MountingType(models.Model):
    _name = 'product.mounting.type'

    name = fields.Char(string='Name')


class ProductFamilyName(models.Model):
    _name = 'product.family.name'

    name = fields.Char(string='Name')


class ProductColor(models.Model):
    _name = 'product.color'

    name = fields.Char(string='Name')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    standard_price = fields.Float(
        'Cost', compute='_compute_standard_price',
        inverse='_set_standard_price', search='_search_standard_price',
        digits='Product Price', groups="egy-trade_custom.group_product_logistics",
        help="""In Standard Price & AVCO: value of the product (automatically computed in AVCO).
            In FIFO: value of the last unit that left the stock (automatically computed).
            Used to value the product when the purchase cost is not known (e.g. inventory adjustment).
            Used to compute margins on sale orders.""")

    family_name = fields.Many2one(comodel_name='product.family.name',
                                  string='Family Name')
    color = fields.Many2one(
        comodel_name='product.color',
                            string='Color', help='Color Corrected Temperature')
    mounting_type = fields.Many2one(comodel_name='product.mounting.type',
                                    string='Mounting Type')
    power = fields.Char(string='Power')
    lumen = fields.Char(string='Lumen')
    product_type_spec = fields.Char(string='Product Type Spec')
    cct = fields.Char(string='CCT')
    ip = fields.Char(string='IP Rating')
    led_voltage = fields.Char(string='LED Voltage')
    driver_manufacture = fields.Char(string='Driver')
    vendor_id = fields.Many2one('product.supplierinfo', name='Manufacture',
                                compute='_compute_vendor_id', store=True)  # domain in view
    manufacturer = fields.Char()
    origin = fields.Char()


    @api.model
    def _insert_data_cron(self):
        sales_orders = self.env['sale.order'].search([])
        purchase_orders = self.env['purchase.order'].search([])
        account_moves = self.env['account.move'].search([])
        for so in sales_orders:
            follower_users = self.env['res.users'].search(
                [('partner_id', 'in', so.message_follower_ids.mapped('partner_id').ids)])
            so.follower_user_ids = [(6, 0, follower_users.ids)]
        for po in purchase_orders:
            follower_users = self.env['res.users'].search(
                [('partner_id', 'in', po.message_follower_ids.mapped('partner_id').ids)])
            po.follower_user_ids = [(6, 0, follower_users.ids)]
        for ac in account_moves:
            follower_users = self.env['res.users'].search(
                [('partner_id', 'in', ac.message_follower_ids.mapped('partner_id').ids)])
            ac.follower_user_ids = [(6, 0, follower_users.ids)]



    @api.depends('seller_ids')
    def _compute_vendor_id(self):
        for rec in self:
            if rec.seller_ids:
                rec.vendor_id = rec.seller_ids[0]
            else:
                rec.vendor_id = False

    cost_change_date = fields.Date(string='Cost Last Updated', compute='_compute_cost_change', store=True,
                                   groups="egy-trade_custom.group_product_logistics")

    @api.depends('standard_price')
    def _compute_cost_change(self):
        for rec in self:
            rec.cost_change_date = date.today()

    list_price = fields.Float(
        'Sales Price', default=1.0,
        digits='Product Price',
        help="Price at which the product is sold to customers.",
        readonly=False,
        store=True
    )

    @api.onchange('margin', 'standard_price')
    def _onchange_list_price(self):
        if self.margin:
            self.list_price = self.standard_price * (1 + (self.margin / 100))

    @api.onchange('list_price')
    def _onchange_margin(self):
        if self.list_price and self.standard_price:
            self.margin = (self.list_price / self.standard_price - 1) * 100
        else:
            self.margin = 0

    margin = fields.Integer(string='Margin',
                            help='Percentage of profit calculated off the cost/standard price',
                            readonly=False,
                            store=True,
                            groups="egy-trade_custom.group_product_logistics"
                            )

    def write(self, values):
        res = super(ProductTemplate, self).write(values)
        return res

    def inventory_update_cron(self):
        pass

    @api.onchange('seller_ids')
    def _compute_standard_price_from_price(self):
        if self.seller_ids:
            vendor_id = self.seller_ids[0]
            if vendor_id.price and vendor_id.currency_id and vendor_id.currency_id.name != 'EGP':
                EGP = self.env['res.currency'].search([('name', '=', 'EGP')])
                today = fields.Date.today()
                new_price = EGP._convert(vendor_id.price, vendor_id.currency_id, self.env.company, today)
                self.standard_price = new_price


class SupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'

    partner_id = fields.Many2one('res.partner')
    @api.depends('partner_id')
    def _compute_delay(self):
        for rec in self:
            rec.delay = rec.partner_id.delay

    delay = fields.Integer(
        'Delivery Lead Time', compute='_compute_delay', required=True, readonly=False,
        help="Lead time in days between the confirmation of the purchase order and the receipt of the products in your warehouse. Used by the scheduler for automatic computation of the purchase order planning.")

    # @api.depends('product_tmpl_id.standard_price')
    # def _compute_price(self):
    #     for rec in self:
    #         rec.price = rec.product_tmpl_id.standard_price

    price = fields.Float(
        'Price', default=0.0, digits='Product Price',
        required=True, help="The price to purchase a product")
