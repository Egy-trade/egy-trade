# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.addons.bus.models.bus_presence import AWAY_TIMER
from odoo.addons.bus.models.bus_presence import DISCONNECTION_TIMER


class ProductProduct(models.Model):
    _inherit = 'product.product'


class ProductTemplate(models.Model):
    _inherit = 'product.template'
