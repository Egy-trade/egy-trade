""" Initialize Crm Lead """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning

from .res_partner import _CRM_CONTACT_CREATE_TOKEN


class CrmLead(models.Model):
    """
        Inherit Crm Lead:
         -
    """
    _inherit = 'crm.lead'

    def _create_customer(self):
        """Allow Odoo's controlled lead-conversion flow to create its customer.

        The in-process token is intentionally scoped to this call.  Direct
        contact creation remains protected by the Create Contact group.
        """
        self.ensure_one()
        return super(
            CrmLead,
            self.with_context(
                _crm_contact_create_token=_CRM_CONTACT_CREATE_TOKEN,
            ),
        )._create_customer()

    @api.model
    def create(self, vals_list):
        """ Override create """
        # vals_list ={'field': value}  -> dectionary contains only new filled fields
        res = super(CrmLead, self).create(vals_list)
        if self.env.user.has_group('oit_contact_restriction.group_restrict_contact'):
            if res.partner_id and res.partner_id not in self.env.user.owner_partner_ids:
                raise ValidationError('You Can Select Only Owners Customer !')
        return res
