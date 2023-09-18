""" Initialize Terms And Conditions """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning


class TermsConditions(models.Model):
    """
        Initialize Terms Conditions:
         -
    """
    _name = 'terms.conditions'
    _description = 'Terms Conditions'
    _sql_constraints = [
        ('unique_name',
         'UNIQUE(name)',
         'Name must be unique'),
    ]
    basic_name = fields.Char(
        string="Name",
        required=True,
    )
    name = fields.Text(
        string="Description",
        required=True,
        translate=True,
    )

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, '%s' % (rec.basic_name)))
        return result
