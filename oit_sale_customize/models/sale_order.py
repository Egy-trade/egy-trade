""" Initialize Model """

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
    terms_conditions_id = fields.Many2one(
        'terms.conditions'
    )

    @api.onchange('terms_conditions_id')
    def _onchange_terms_conditions_id(self):
        """ terms_conditions_id """
        for rec in self:
            if rec.terms_conditions_id:
                rec.write({
                    'note': rec.terms_conditions_id.name
                })
