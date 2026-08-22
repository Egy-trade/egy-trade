""" Initialize Crm Lead """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning

from .res_partner import (
    CRM_LEAD_CUSTOMER_CONTEXT_KEY,
    CRM_LEAD_CUSTOMER_CONTEXT_TOKEN,
)


class CrmLead(models.Model):
    """
        Inherit Crm Lead:
         -
    """
    _inherit = 'crm.lead'

    def _create_customer(self):
        """ Authorize the partner creations performed by this method.

        The lead conversion flow (quotation wizard, _handle_partner_assignment,
        convert_opportunity) legitimately creates customers for salespeople who
        must not create contacts manually; it carries the private in-process
        token so res.partner.create can tell the two paths apart. The context
        is applied to ``self`` before entering ``super()`` so the parent
        implementation runs exactly once on the token-carrying recordset.
        """
        return super(CrmLead, self.with_context(
            **{CRM_LEAD_CUSTOMER_CONTEXT_KEY: CRM_LEAD_CUSTOMER_CONTEXT_TOKEN},
        ))._create_customer()

    @api.model
    def create(self, vals_list):
        """ Override create """
        # vals_list ={'field': value}  -> dectionary contains only new filled fields
        res = super(CrmLead, self).create(vals_list)
        if self.env.user.has_group('oit_contact_restriction.group_restrict_contact'):
            if res.partner_id and res.partner_id not in self.env.user.owner_partner_ids:
                raise ValidationError('You Can Select Only Owners Customer !')
        return res
