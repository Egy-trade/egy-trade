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

    @api.model
    def create(self, vals_list):
        """ Override create """
        # vals_list ={'field': value}  -> dectionary contains only new filled fields
        res = super(CrmLead, self).create(vals_list)
        if self.env.user.has_group('oit_contact_restriction.group_restrict_contact'):
            if res.partner_id and res.partner_id not in self.env.user.owner_partner_ids:
                raise ValidationError('You Can Select Only Owners Customer !')
        return res
