""" Initialize Crm Lead """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning


class CrmLead(models.Model):
    """
        Inherit Crm Lead:
         -
    """
    _inherit = 'crm.lead'

    lighting_designer_id = fields.Many2one(
        'res.users'
    )
    technical_sales_id = fields.Many2one(
        'res.users'
    )
    technical_office_id = fields.Many2one(
        'res.users'
    )

    def _prepare_opportunity_quotation_context(self):
        """ Override _prepare_opportunity_quotation_context """
        res = super(CrmLead, self)._prepare_opportunity_quotation_context()
        res['default_lighting_designer_id'] = self.lighting_designer_id.id
        res['default_technical_sales_id'] = self.technical_sales_id.id
        res['default_technical_office_id'] = self.technical_office_id.id
        return res
