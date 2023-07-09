""" Initialize Res Partner """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning


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

    @api.model
    def create(self, vals_list):
        """ Override create """
        # vals_list ={'field': value}  -> dectionary contains only new filled fields
        res = super(ResPartner, self).create(vals_list)
        if not self.env.user.has_group('oit_contact_restriction.group_create_contact'):
            raise ValidationError('You must have create contact group !')
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
