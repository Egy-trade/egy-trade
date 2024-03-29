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

    mep_contractors = fields.Many2one(
        'res.users'
    )
    arch_consultants = fields.Many2one(
        'res.users'
    )
    electrical_consultants = fields.Many2one(
        'res.users'
    )