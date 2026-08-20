# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


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
    mep_contractors = fields.Many2one('res.users', string='MEP Contractor')
    arch_consultants = fields.Many2one('res.users', string='Architecture Consultant')
    electrical_consultants = fields.Many2one('res.users', string='Electrical Consultant')
    project = fields.Char(help='Project name shown on the quotation when selected for PDF output.')
    print_manufacturer = fields.Boolean(
        string='Print Manufacturer', default=True, copy=True,
        help='Include the Manufacturer column in this quotation PDF.',
    )
    print_origin = fields.Boolean(
        string='Print Origin', default=True, copy=True,
        help='Include the country-of-origin column in this quotation PDF.',
    )
    print_project = fields.Boolean(
        string='Print Project', default=True, copy=True,
        help='Include the Project value in this quotation PDF.',
    )
    
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

    # def read(self, records):
    #     for rec in self:
    #         if self.env.user.has_group('egy-trade_custom.group_egy_trade_user') and not self.env.user.has_group('sales_team.group_sale_manager') and self.env.uid not in rec.follower_user_ids.ids:
    #             raise ValidationError("You are not allowed to access this document !")
    #     res = super(SaleOrder, self).read(records)
    #     return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    margin = fields.Float(
        "Margin", compute='_compute_margin',
        digits='Product Price', store=True, groups="egy-trade_custom.group_product_logistics")
    margin_percent = fields.Float(
        "Margin (%)", compute='_compute_margin', store=True, groups="egy-trade_custom.group_product_logistics")
    purchase_price = fields.Float(
        string='Accounting Cost', compute="_compute_purchase_price",
        digits='Product Price', store=True, readonly=False,
        )

    product_vendor = fields.Many2one(related='product_id.vendor_id')
    product_family_name = fields.Many2one(related='product_id.family_name')
    product_power = fields.Char(related='product_id.power')
    product_ip = fields.Char(related='product_id.ip')
    product_lumen = fields.Char(related='product_id.lumen')
    manufacturer = fields.Char(related='product_id.manufacturer')
    origin = fields.Char(related='product_id.origin')
    sn = fields.Char('SN')

    @api.constrains('discount')
    def _check_discount(self):
        user = self.env.user
        pricing_group = self.env.ref(
            'sale_order_product_pricing.product_pricing_group',
            raise_if_not_found=False,
        )
        has_full_pricing = (
            self.env.is_superuser()
            or user.has_group('sales_team.group_sale_manager')
            or (pricing_group and pricing_group in user.groups_id)
        )
        if has_full_pricing:
            return
        for rec in self:
            enabled = getattr(rec.company_id, 'standard_discount_enabled', True)
            company_limit = getattr(rec.company_id, 'standard_discount_maximum', 30.0)
            if not enabled and rec.discount:
                raise ValidationError(_(
                    'Standard line discounts are disabled in Sales Settings.'
                ))
            limit = min(
                max(user.max_discount or 0.0, 0.0),
                max(company_limit or 0.0, 0.0),
                30.0,
            )
            if (
                    float_compare(rec.discount, 0.0, precision_digits=6) < 0
                    or float_compare(rec.discount, limit, precision_digits=6) > 0):
                raise ValidationError(_(
                    'Your maximum allowed standard discount per order line is %(limit).2f%%.'
                ) % {'limit': limit})

    @api.constrains('name')
    def _check_name_c(self):
        """Keep an already-linked purchase line description synchronized.

        A quotation specialist is allowed to prepare sale-order lines without
        Purchase access.  The relation is internal workflow data, so the
        lookup and the narrowly-scoped description update run with system
        rights rather than requiring the sale-line editor to read or write
        purchase records.
        """
        for rec in self:
            purchase_line_ids = self.env['purchase.order.line'].sudo().search([
                ('sale_line_id','=', rec.id)
            ])
            purchase_line_ids.write({'name': rec.name})
