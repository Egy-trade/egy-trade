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

    # mep_contractor = fields.Many2one(
    #     'res.users'
    # )
    arch_consultant = fields.Many2one(
        'res.users'
    )
    electrical_consultant = fields.Many2one(
        'res.users'
    )