""" Initialize Sale Order """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning


class SaleOrder(models.Model):
    """
        Inherit Sale Order:
         -
    """
    _inherit = 'sale.order'

    lighting_designer_id = fields.Many2one(
        'res.users'
    )
    technical_sales_id = fields.Many2one(
        'res.users'
    )
    technical_office_id = fields.Many2one(
        'res.users'
    )