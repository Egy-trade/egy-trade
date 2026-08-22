""" Initialize Res Partner """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning

# Context key and private in-process token authorizing the customer creation
# performed by the CRM lead conversion flow (crm.lead._create_customer); see
# crm_lead.py. The value is an object() identity: JSON/RPC clients can only
# send JSON-serializable context values, so they cannot reproduce object
# identity and cannot forge this authorization.
CRM_LEAD_CUSTOMER_CONTEXT_KEY = 'oit_contact_restriction_crm_lead_customer'
CRM_LEAD_CUSTOMER_CONTEXT_TOKEN = object()


class ResPartner(models.Model):
    """
        Inherit Res Partner:
         -
    """
    _inherit = 'res.partner'

    allowed_users_ids = fields.Many2many(
        'res.users',
        relation='users_allowed_partner',
        coulmn1='partner_id',
        coulmn2='user_id',
    )
    owner_users_ids = fields.Many2many(
        'res.users',
        relation='users_owner_partner',
        coulmn1='partner_id',
        coulmn2='user_id',
    )
    is_user = fields.Boolean()

    @api.model_create_multi
    def create(self, vals_list):
        """ Override create

        Manual contact creation stays restricted to members of the Create
        Contact group. Customer creation triggered by the CRM lead conversion
        flow is authorized by its private context token; forged context
        values (booleans/strings) never match token identity.

        ``@api.model_create_multi`` accepts both a single dict and a list of
        dicts; validation runs before any record is created.
        """
        if not (
            self.env.context.get(CRM_LEAD_CUSTOMER_CONTEXT_KEY) is CRM_LEAD_CUSTOMER_CONTEXT_TOKEN
            or self.env.user.has_group('oit_contact_restriction.group_create_contact')
        ):
            raise ValidationError('You must have create contact group !')
        res = super(ResPartner, self).create(vals_list)
        res._onchange_allowed_users_ids()
        res._onchange_owner_users_ids()
        self.env['ir.rule'].clear_caches()
        return res

    @api.constrains('allowed_users_ids', 'write_date')
    def _onchange_allowed_users_ids(self):
        """ allowed_users_ids """
        for rec in self:
            if rec.allowed_users_ids:
                for user in rec.allowed_users_ids:
                    user.allowed_partner_ids |= rec

    @api.constrains('owner_users_ids', 'write_date')
    def _onchange_owner_users_ids(self):
        """ allowed_users_ids """
        for rec in self:
            if rec.owner_users_ids:
                for user in rec.owner_users_ids:
                    user.owner_partner_ids |= rec
