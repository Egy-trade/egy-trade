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

    def _update_invnetory_cron(self):
        pass

    def _insert_data_cron(self):
        name = [
            63,
            63,
            63,
            63,
            63,
            63,
            63,
            63,
            63,
            63,
            63,
            63,
            43,
            43,
            43,
            43,
            43,
            62,
            62,
            62,
            62,
            60,
            60,
            60,
            64,
            64,
            64,
            64,
            47,
            47,
            47,
            43,
            43,
            43,
            43,
            43,
            43,
            43,
            49,
            49,
            49,
            49,
            49,
            49,
            49,
            49,
            49,
            49,
            49,
            63,
            50,
            50,
            50,
            55,
            49,
            65,
            65,
            56,
            56,
            56,
            56,
            56,
            56,
            56,
            56,
            56,
            46,
            46,
            46,
            46,
            46,
            46,
            46,
            46,
            46,
            46,
            59,
            59,
            43,
            43,
            48,
            48,
            48,
            50,
            50,
            45,
            58,
            58,
            58,
            58,
            58,
            58,
            58,
            58,
            58,
            43,
            43,
            66,
            62,
            46,
            61,
            61,
            61,
            55,
            68,
            67,
            67,
            67,
            67,
            67,
            69,
            63,
            63,
            63,
            63,
            66,
            63,
            60,
            63,
            63,
            56,
            56,
            56,
            56,
            56,
            44,
            55,
            69,
            62,
            54,
            54,
            70,
            50,
            50,
            50,
            50,
            50,
            56,
            59,
            63,
            63,
            63,
            63,
            58,
            58,
            58,
            58,
            58,
            58,
            58,
            58,
            62,
            68,
            56,
            61,
            43,
            58,
            58,
            58,
            58,
            58,
            58,
            58,
            58,
            58,
            58,
            58,
            58,
            58,
            74,
            74,
            74,
            57,
            57,
            57,
            44,
            59,
            59,
            49,
            71,
            71,
            57,
            57,
            58,
            57,
            72,
            72,
            72,
            72,
            49,
            50,
            50,
            62,
            58,
            63,
            66,
            66,
            47,
            59,
            59,
            59,
            75,
            76,
            76,
            58,
            58,
            58,
            56,
            56,
            56,
            56,
            56,
            56,
            56,
            57,
            63,
            73,
            73,
            73,
            60,
            63,
        ]
        products = [
            222,
            223,
            224,
            225,
            226,
            227,
            228,
            229,
            230,
            437,
            232,
            233,
            234,
            235,
            236,
            237,
            238,
            239,
            240,
            241,
            242,
            243,
            244,
            245,
            246,
            247,
            248,
            249,
            250,
            251,
            252,
            253,
            254,
            255,
            256,
            257,
            258,
            259,
            260,
            261,
            262,
            263,
            264,
            265,
            266,
            267,
            269,
            269,
            270,
            271,
            272,
            273,
            274,
            275,
            276,
            277,
            278,
            279,
            280,
            281,
            282,
            283,
            284,
            285,
            286,
            287,
            288,
            289,
            290,
            291,
            292,
            293,
            294,
            295,
            296,
            297,
            298,
            299,
            300,
            301,
            302,
            303,
            304,
            305,
            306,
            307,
            308,
            309,
            310,
            311,
            312,
            313,
            314,
            315,
            316,
            317,
            318,
            319,
            320,
            321,
            322,
            323,
            324,
            325,
            326,
            327,
            328,
            329,
            330,
            331,
            332,
            333,
            334,
            335,
            336,
            337,
            338,
            339,
            340,
            341,
            342,
            343,
            344,
            345,
            346,
            347,
            348,
            349,
            350,
            351,
            352,
            353,
            354,
            355,
            356,
            357,
            358,
            359,
            360,
            361,
            362,
            363,
            364,
            365,
            366,
            367,
            368,
            369,
            370,
            371,
            372,
            373,
            374,
            375,
            376,
            377,
            378,
            379,
            380,
            381,
            382,
            383,
            384,
            385,
            386,
            387,
            388,
            389,
            390,
            391,
            392,
            393,
            394,
            395,
            396,
            397,
            398,
            399,
            400,
            401,
            402,
            403,
            404,
            405,
            406,
            407,
            408,
            409,
            410,
            411,
            412,
            413,
            414,
            415,
            416,
            417,
            418,
            419,
            420,
            421,
            422,
            423,
            424,
            425,
            426,
            427,
            428,
            429,
            430,
            431,
            432,
            433,
            434,
            435,
            436,
            437,
            438,
            439,
            440,
            441,
            442,
        ]
        print('\nBEGIN LOOP')
        for p, v in zip(products, name):
            p_obj = self.env['product.template'].browse(p)
            print(f'Product: {p}, Vendor: {v}, obj: {p_obj}')
            print()
            p_obj.write({
                'invoice_policy': 'order',
                'purchase_method': 'purchase',
                'tracking': 'lot',
            })
            # supp = self.env['product.supplierinfo'].create({
            #     'name': v,
            #     'product_tmpl_id': p
            # })
            # print('supp', supp)
        print('\nEND LOOP')
        return True


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
