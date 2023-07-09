""" Initialize Res Users """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning


class ResUsers(models.Model):
    """
        Inherit Res Users:
         -
    """
    _inherit = 'res.users'

    allowed_partner_ids = fields.Many2many(
        'res.partner',
        relation='users_allowed_partner',
        coulmn1='partner_id',
        coulmn2='user_id',
        # compute='_compute_allowed_partner_ids'
    )
    owner_partner_ids = fields.Many2many(
        'res.partner',
        relation='users_owner_partner',
        coulmn1='partner_id',
        coulmn2='user_id',
        # compute='_compute_owner_partner_ids'
    )

    # def _compute_owner_partner_ids(self):
    #     """ Compute owner_partner_ids value """
    #     for rec in self:
    #         partners = self.env['res.partner'].search([
    #             ('allowed_partner_ids')
    #         ])

    def update_is_user(self):
        """ Update Is User """
        users = self.env['res.users'].search([])
        for user in users:
            user.partner_id.is_user = True
