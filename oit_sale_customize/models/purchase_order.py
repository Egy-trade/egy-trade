""" Initialize Purchase Order """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning


class PurchaseOrder(models.Model):
    """
        Inherit Purchase Order:
         -
    """
    _inherit = 'purchase.order'

    terms_conditions_id = fields.Many2one(
        'po.terms.conditions'
    )

    @api.onchange('terms_conditions_id')
    def _onchange_terms_conditions_id(self):
        """ terms_conditions_id """
        for rec in self:
            if rec.terms_conditions_id:
                rec.write({
                    'notes': rec.terms_conditions_id.name
                })
