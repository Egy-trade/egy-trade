# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    state = fields.Selection([
        ('draft', 'Quotation'),
        ('approve', 'Approved'),
        ('sent', 'Quotation Sent'),
        ('sale', 'Sales Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, index=True, tracking=3, default='draft')
    follower_user_ids = fields.Many2many('res.users', compute="_get_follower_user_ids", store=True)

    @api.depends('message_follower_ids')
    def _get_follower_user_ids(self):
        for rec in self:
            follower_users = self.env['res.users'].search([('partner_id', 'in', rec.message_follower_ids.mapped('partner_id').ids)])
            rec.follower_user_ids = [(6, 0, follower_users.ids)]

    # Incomplete validation of the approved state
    def action_to_approve(self):
        self.state = 'approve'

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

    def read(self, records):
        for rec in self:
            if self.env.user.has_group('egy-trade_custom.group_egy_trade_user') and not self.env.user.has_group('sales_team.group_sale_manager') and self.env.uid not in rec.follower_user_ids.ids:
                raise ValidationError("You are not allowed to access this document !")
        res = super(SaleOrder, self).read(records)
        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    margin = fields.Float(
        "Margin", compute='_compute_margin',
        digits='Product Price', store=True, groups="egy-trade_custom.group_product_logistics")
    margin_percent = fields.Float(
        "Margin (%)", compute='_compute_margin', store=True, groups="egy-trade_custom.group_product_logistics")
    purchase_price = fields.Float(
        string='Cost', compute="_compute_purchase_price",
        digits='Product Price', store=True, readonly=False,
        groups="egy-trade_custom.group_product_logistics")

    product_vendor = fields.Many2one(related='product_id.vendor_id')
    product_family_name = fields.Many2one(related='product_id.family_name')
    product_power = fields.Char(related='product_id.power')
    product_ip = fields.Char(related='product_id.ip')
    product_lumen = fields.Char(related='product_id.lumen')

    @api.constrains('discount')
    def _check_discount(self):
        for rec in self:
            if rec.discount > self.env.user.max_discount:
                raise ValidationError(_(f'Your maximum allowed discount per order line is {self.env.user.max_discount}'))

