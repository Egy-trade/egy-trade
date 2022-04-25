# -*- coding: utf-8 -*-

from random import randint
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PurchaseTag(models.Model):
    _name = 'purchase.tag'

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char(string="Name")
    color = fields.Integer(string='Color Index', default=_get_default_color)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        self.order_line = False

    @api.depends('partner_id')
    def _get_partner_allows(self):
        user = self.env.user
        all_teams = self.env['crm.team'].search([('user_id', '=', user.id)])
        team_list = [team.id for team in all_teams]
        is_team_leader = self.env.user.has_group('egy-trade_custom.salas_team_leader')
        if user.has_group('sales_team.group_sale_manager'):
            partners = self.env['res.partner'].search([('active', '=', True)])
        elif team_list and is_team_leader:
            partners = self.env['res.partner'].search([('team_id', 'in', team_list)])
            print("Partner Teams Leader ", partners)
        else:
            partners = self.env['res.partner'].search([('user_id', '=', user.id)])
            print("Partners", partners)
        self.partner_allow_ids = partners

    partner_allow_ids = fields.Many2many('res.partner', compute='_get_partner_allows')
    p_tag_ids = fields.Many2many('purchase.tag',string="Tags")
    follower_user_ids = fields.Many2many('res.users', compute="_get_follower_user_ids", store=True)

    @api.depends('message_follower_ids')
    def _get_follower_user_ids(self):
        for rec in self:
            follower_users = self.env['res.users'].search(
                [('partner_id', 'in', rec.message_follower_ids.mapped('partner_id').ids)])
            rec.follower_user_ids = [(6, 0, follower_users.ids)]


    def read(self, records):
        for rec in self:
            if self.env.user.has_group('egy-trade_custom.group_egy_trade_user') and not self.env.user.has_group('purchase.group_purchase_manager')and self.env.uid not in rec.follower_user_ids.ids:
                raise ValidationError("You are not allowed to access this document !")
        res = super(PurchaseOrder, self).read(records)
        return res

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    product_vendor = fields.Many2one(related='product_id.vendor_id')
    product_family_name = fields.Many2one(related='product_id.family_name')
    product_power = fields.Char(related='product_id.power')
    product_ip = fields.Char(related='product_id.ip')
    product_lumen = fields.Char(related='product_id.lumen')
