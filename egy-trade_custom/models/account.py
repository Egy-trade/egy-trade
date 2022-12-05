# -*- coding: utf-8 -*-

from random import randint
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    follower_user_ids = fields.Many2many('res.users', compute="_get_follower_user_ids", store=True)

    @api.depends('message_follower_ids')
    def _get_follower_user_ids(self):
        for rec in self:
            follower_users = self.env['res.users'].search(
                [('partner_id', 'in', rec.message_follower_ids.mapped('partner_id').ids)])
            rec.follower_user_ids = [(6, 0, follower_users.ids)]

    def read(self, records):
        for rec in self:
            if self.env.user.has_group('egy-trade_custom.group_egy_trade_user') and not self.env.user.has_group('account.group_account_manager') and self.env.uid not in rec.follower_user_ids.ids:
                raise ValidationError("You are not allowed to access this document !")
        res = super(AccountMove, self).read(records)
        return res
