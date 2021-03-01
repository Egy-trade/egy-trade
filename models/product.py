# -*- coding: utf-8 -*-
from odoo import models, fields


class MountingType(models.Model):
    _name = 'product.mounting.type'

    name = fields.Char(string='Name')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    family_name = fields.Char(string='Family Name')
    color = fields.Char(string='Color')
    power = fields.Char(string='Power')
    lumen = fields.Char(string='Lumen')
    product_code = fields.Char(string='Product Code')
    cct = fields.Char(string='CCT')
    ip = fields.Char(string='IP Rating')
    led_voltage = fields.Char(string='LED Voltage')


class Product(models.Model):
    _inherit = 'product.product'
