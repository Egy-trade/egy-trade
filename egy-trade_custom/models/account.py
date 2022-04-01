# -*- coding: utf-8 -*-

from random import randint
from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    follower_user_ids = fields.Many2many('res.users', compute="_get_follower_user_ids", store=True)

    @api.depends('message_follower_ids')
    def _get_follower_user_ids(self):
        for rec in self:
            follower_users = self.env['res.users'].search(
                [('partner_id', 'in', rec.message_follower_ids.mapped('partner_id').ids)])
            rec.follower_user_ids = [(6, 0, follower_users.ids)]