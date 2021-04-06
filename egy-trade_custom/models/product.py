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

    family_name = fields.Many2one(comodel_name='product.family.name',
                                  string='Family Name')
    color = fields.Many2one(comodel_name='product.color',
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
                                compute='_compute_vendor_id')  # domain in view

    @api.depends('seller_ids')
    def _compute_vendor_id(self):
        for rec in self:
            if rec.seller_ids:
                rec.vendor_id = rec.seller_ids[0]
            else:
                rec.vendor_id = False

    cost_change_date = fields.Date(string='Cost Last Updated', compute='_compute_cost_change', store=True)

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
        if self.list_price:
            self.margin = (self.list_price / self.standard_price - 1) * 100
        else:
            self.margin = 0

    margin = fields.Integer(string='Margin',
                            help='Percentage of profit calculated off the cost/standard price',
                            readonly=False,
                            store=True
                            )

    def write(self, values):
        res = super(ProductTemplate, self).write(values)
        return res

    def _insert_data_cron(self):
        df = pd.read_excel('/home/odoo/src/user/client_data/product_template.xlsx', sheet_name='Template')
        # df = pd.read_excel("C:\\Users\\Rottab\\Dev\\Odoo\\odoo-14.0-enterprise\\custom-addons\\egy-trade\\client_data\\product_template.xlsx", sheet_name='Template')
        for _, pt in df.iterrows():
            pt_obj = self.env['product.template'].search([('name', '=', str(pt['Name']))], limit=1)
            vendor_id = self.env['res.partner'].search([('name', '=', str(pt['Vendors']))])
            self.env['product.supplierinfo'].create({
                'name': vendor_id.id,
                'product_tmpl_id': pt_obj.id
            })


class SupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'

    @api.depends('name')
    def _compute_delay(self):
        for rec in self:
            rec.delay = rec.name.delay

    delay = fields.Integer(
        'Delivery Lead Time', compute='_compute_delay', required=True, readonly=False,
        help="Lead time in days between the confirmation of the purchase order and the receipt of the products in your warehouse. Used by the scheduler for automatic computation of the purchase order planning.")

    @api.depends('product_tmpl_id.standard_price')
    def _compute_price(self):
        for rec in self:
            rec.price = self.product_tmpl_id.standard_price

    price = fields.Float(
        'Price', default=0.0, digits='Product Price',
        required=True, help="The price to purchase a product", compute='_compute_price', readonly=True, store=True)
