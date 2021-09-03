# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class Users(models.Model):
    _inherit = 'res.users'

    # max_discount = fields.Integer(string='Max Discount')
