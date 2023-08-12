# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class FinalLetterGuarantee(models.Model):
    _name = 'final.letter.guarantee'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('close', 'Close'),
        ('reject', 'Rejected'),
    ], string='Status', index=True, readonly=True, default='draft',
        track_visibility='onchange', copy=False)
    company_id = fields.Many2one('res.company', string='Company', readonly=True
                                 , default=lambda self: self.env.user.company_id)
    project = fields.Char('Project Name', track_visibility='always')
    lg_ref = fields.Char('LG Ref', track_visibility='always')
    name = fields.Char('Name', default='New', readonly=True, copy=False, track_visibility='onchange', )
    partner_id = fields.Many2one('res.partner', string='Issued For', required=True,
                                 track_visibility='onchange', )
    currency_id = fields.Many2one('res.currency', 'Currency', required=True, store=True,
                                  track_visibility='onchange',default=lambda self: self.env.user.company_id.currency_id)
    amount = fields.Monetary(currency_field='currency_id', string='LG Amount', default=0.00,required=True, store=True,readonly=True)
    journal_id = fields.Many2one('account.journal', string='Bank Account', domain=[('type', '=', 'bank')],
                                 required=True, track_visibility='onchange', )
    bank_id = fields.Many2one(related='journal_id.bank_id', string='Bank', readonly='1', store=True)
    analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account', track_visibility='onchange', )
    date_issue = fields.Date('Issue Date', required=True, track_visibility='onchange', )
    expire_date = fields.Date('Expiry Date', required=True, track_visibility='onchange', )
    type = fields.Selection([
        ('initial', 'خطاب ضمان ابتدائي'),
        ('final', 'خطاب ضمان نهائي'),
    ], string='Type', default='final', readonly=True,
        track_visibility='onchange')
    notice = fields.Text('Notice')
    request_lg_id = fields.Many2one('final.request.letter.guarantee', string='Source Ref', store=True, readonly=True)
    tax = fields.Float(string='Tax Amount', default=0.00)
    bank_amount = fields.Float(string='Project Cost (%)')

    def get_move_lines(self):
        return {
            'name': 'Moves',
            # 'view_type': 'form',
            'domain': [('move_id.ref', '=', self.name)],
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    def button_inprogress(self):
        if not self.journal_id.final_account_id or not self.journal_id.project_account_id \
                or not self.journal_id.tax_credit_account_id or not self.journal_id.final_lg_account_id:
            raise UserError(_('Please check letter of guarantee accounts!'))
        if self.journal_id and self.amount and self.date_issue:
            bank_facilties = self.env['bank.facilities'].search(
                [('bank_account_id', '=', self.journal_id.id), ('type', '=', self.type),
                 ('end_date', '>=', self.date_issue),
                 ('start_date', '<=', self.date_issue), ('state', '=', 'confirm')], limit=1)
            if bank_facilties:
                for bank in bank_facilties:
                    if bank.remaining < self.amount:
                        raise UserError(_('Sorry, Amount greater than bank facility!'))
                    else:
                        bank.current_balance = bank.current_balance + self.amount
            else:
                raise UserError(_('Sorry, there is no bank facility for this journal!'))

        self.state = 'in_progress'
        lines = [
            (0, 0, {
                'name': 'خطاب الضمان النهائي ',
                'account_id': self.journal_id.final_account_id.id,
                'credit': 0,
                'analytic_account_id': self.analytic_id.id,
                'debit': self.amount * (self.journal_id.cover_percentage / 100),
                'partner_id': self.partner_id.id,
                'date_maturity': self.date_issue,
            }),
            (0, 0, {
                'name': 'تكلفة المشروع',
                'account_id': self.journal_id.project_account_id.id,
                'credit': 0,
                'analytic_account_id': self.analytic_id.id,
                'debit': (self.bank_amount / 100) * self.amount,
                'partner_id': self.partner_id.id,
                'date_maturity': self.date_issue,
            }),
            (0, 0, {
                'name': 'الضريبة',
                'account_id': self.journal_id.tax_credit_account_id.id,
                'credit': 0,
                'analytic_account_id': self.analytic_id.id,
                'debit': self.tax,
                'partner_id': self.partner_id.id,
                'date_maturity': self.date_issue,
            }),
            (0, 0, {
                'name': '/',
                'account_id': self.journal_id.default_account_id.id,
                'credit': self.tax + (self.amount * (self.journal_id.cover_percentage / 100)) + (
                        self.bank_amount / 100) * self.amount,
                'debit': 0,
                'partner_id': self.partner_id.id,
                'date_maturity': self.date_issue,
            }),
            (0, 0, {
                'name': 'تعهدات خطاب الضمان',
                'account_id': self.journal_id.final_lg_account_id.id,
                'debit': 0,
                'analytic_account_id': self.analytic_id.id,
                'credit': self.amount * ((100 - self.journal_id.cover_percentage) / 100),
                'partner_id': self.partner_id.id,
                'date_maturity': self.date_issue,
            }),
            (0, 0, {
                'name': '/',
                'account_id': self.journal_id.lg_account_id.id,
                'debit': self.amount * ((100 - self.journal_id.cover_percentage) / 100),
                'credit': 0,
                'partner_id': self.partner_id.id,
                'date_maturity': self.date_issue,
            })

        ]
        move_id = self.env['account.move'].create({
            'date': fields.Date.today(),
            'journal_id': self.journal_id.id,
            'ref': self.name,
            'line_ids': lines,
        })
        move_id.post()

    def button_close(self):
        self.state = 'close'

    @api.onchange('amount')
    @api.constrains('amount')
    def amount_validation(self):
        if self.amount and self.amount < 0:
            raise UserError(_('The Amount must be greater than Zero!'))

    @api.onchange('date_issue', 'expire_date')
    @api.constrains('date_issue', 'expire_date')
    def validation_on_expiry_date(self):
        if self.date_issue and self.expire_date:
            if self.date_issue > self.expire_date:
                raise UserError(_('Sorry,Expiry Date should be greater than Issued date!'))

    @api.onchange('expire_date')
    @api.constrains('expire_date')
    def validation_on_expiry_date_today(self):
        if self.expire_date:
            if self.expire_date <= fields.Date.today():
                raise UserError(_('Sorry,Expiry Date should be greater than today date!'))

    # @api.one
    def post(self):
        if self.request_lg_id:
            self.request_lg_id.write({'state': 'done', 'lg_id': self.id})
        return True

    @api.constrains('journal_id','amount','date_issue')
    def get_validate_lg(self):
        if self.journal_id and self.amount and self.date_issue:
            bank_facilties = self.env['bank.facilities'].search(
                [('bank_account_id', '=', self.journal_id.id),('type','=',self.type), ('end_date', '>=', self.date_issue),
                 ('start_date', '<=', self.date_issue), ('state', '=', 'confirm')], limit=1)
            if bank_facilties:
                for bank in bank_facilties:
                    if bank.remaining < self.amount:
                        raise UserError(_('Sorry, Amount greater than bank facility!'))
            else:
                raise UserError(_('Sorry, there is no bank facility for this journal!'))

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('final.letter.guarantee') or 'New'
        lg = models.Model.create(self, vals)
        return lg
