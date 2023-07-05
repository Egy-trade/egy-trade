# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class BankFacilities(models.Model):
    _name = 'bank.facilities'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
    ], string='Status', index=True, readonly=True, default='draft',
        track_visibility='onchange', copy=False)
    name = fields.Char(default='Bank Facilities')
    bank_account_id = fields.Many2one('account.journal', string='Bank Account', domain=[('type', '=', 'bank')],
                                      required=True, track_visibility='onchange', )
    currency_id = fields.Many2one(
        'res.currency', 'Currency', required=True,
        default=lambda self: self.env.user.company_id.currency_id)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.user.company_id)
    start_date = fields.Date(string='Start Date', default=fields.Date.context_today, required=True, copy=False)
    end_date = fields.Date(string='End Date', default=fields.Date.context_today, copy=False, required=True)
    initial_balance = fields.Monetary('Initial Balance', currency_field='currency_id', default=0.0)
    current_balance = fields.Monetary('Current Balance', currency_field='currency_id', default=0.0, readonly=True)
    remaining = fields.Monetary('Remaining', currency_field='currency_id', default=0.0, readonly=True,
                                compute='_compute_remaining_amount')
    type = fields.Selection([
        ('initial', 'خطاب ضمان ابتدائي'),
        ('final', 'خطاب ضمان نهائي'),
    ], string='Type', default='initial')

    def button_confirm(self):
        self.state = 'confirm'

    @api.depends('initial_balance', 'current_balance')
    def _compute_remaining_amount(self):
        for record in self:
            record.remaining = record.initial_balance - record.current_balance
