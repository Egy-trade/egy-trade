# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class LetterGuarantee(models.Model):
    _name = 'letter.guarantee'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    name = fields.Char('Name', default='New', readonly=True,store=True)
    partner_id = fields.Many2one('res.partner', string='Issued For', required=True)
    currency_id = fields.Many2one('res.currency', 'Currency',required=True,store=True)
    amount = fields.Monetary(currency_field='currency_id', string='Amount',required=True,store=True)
    journal_id = fields.Many2one('account.journal', string='Bank Account', domain=[('type', '=', 'bank')],required=True)
    bank_id = fields.Many2one(related='journal_id.bank_id', string='Bank',readonly='1',store=True)
    analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    date_issue = fields.Date('Issue Date',required=True)
    expire_date = fields.Date('Expiry Date', required=True)
    type = fields.Selection([
        ('advance', 'Advance Payment'),
        ('bid_bond', 'Bid Bond'),
        ('performance_bond', 'Performance Bond'),
    ], string='Type', default='advance',
        track_visibility='onchange')
    notice = fields.Text('Notice')
    cover_percentage = fields.Float(string='Cover Per',default=100.0)
    request_lg_id = fields.Many2one('request.letter.guarantee',string='LG Request',store=True,readonly=True)

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
                raise UserError(_('The Expiry Date must be greater than Issued for date!'))

    @api.onchange('expire_date')
    @api.constrains('expire_date')
    def validation_on_expiry_date_today(self):
        if self.expire_date:
            if self.expire_date <= fields.Date.today():
                raise UserError(_('The Expiry Date must be greater than today date!'))



    @api.model
    def automate_lg_messages(self):
        lgs = self.env['letter.guarantee'].search([('expire_date', '>=', fields.Date.today())])
        if lgs:
            for lg in lgs:
                self.env['mail.message'].sudo().create({
                    'subject': 'LG Message ' + lg.name,
                    'body': 'Dear All, kindly review ' + str(lg.name) +
                            ' will expire soon ' + str(
                        lg.expire_date) + ' please take the next action to close or extend it.',
                    'author_id': self.env.user.partner_id.id,
                    'needaction_partner_ids': [(6, 0, self.env.user.ids)],
                    'message_type': 'email',
                    'moderation_status': 'pending_moderation',
                    'partner_ids': [(6, 0,self.env.user.ids)]})

    def move(self,account_credit,account_debit,date,name):
        lines = [
            (0, 0, {
                'name': 'LG',
                'account_id': account_credit,
                'debit': 0,
                'credit': self.amount * (self.cover_percentage / 100),
                'partner_id': self.partner_id.id,
                'date_maturity': date,
            }),
            (0, 0, {
                'name': '/',
                'account_id': account_debit,
                'debit': self.amount * (self.cover_percentage / 100),
                'credit': 0,
                'partner_id': self.partner_id.id,
                'date_maturity': date,
            })
        ]
        move_id = self.env['account.move'].create({
            'date': fields.Date.today(),
            'journal_id': self.journal_id.id,
            'ref':name,
            'line_ids': lines,
        })
        move_id.post()

    def action_validate(self):
        if self.expire_date and self.expire_date <= fields.Date.today():
            if self.expire_date <= fields.Date.today():
                raise UserError(_('The Expiry Date must be greater than today date!'))
        elif self.date_issue and self.expire_date and self.date_issue > self.expire_date:
            if self.date_issue > self.expire_date:
                raise UserError(_('The Expiry Date must be greater than Issued for date!'))
        else:
            self.move(self.journal_id.default_account_id.id,self.env.user.company_id.guarantee_journal_id.id,fields.Date.today(),self.name)

    def action_close(self):
        if self.expire_date and self.expire_date <= fields.Date.today():
            if self.expire_date <= fields.Date.today():
                raise UserError(_('The Expiry Date must be greater than today date!'))
        elif self.date_issue and self.expire_date and self.date_issue > self.expire_date:
            if self.date_issue > self.expire_date:
                raise UserError(_('The Expiry Date must be greater than Issued for date!'))
        else:
            self.move(self.env.user.company_id.guarantee_journal_id.id,self.journal_id.default_account_id.id,fields.Date.today(),str("Refund of "+self.name))
    # @api.one
    def post(self):
        if self.request_lg_id:
            self.request_lg_id.write({'state': 'in_progress','lg_id':self.id})
            self.action_validate()
        return True

    def action_validate_lg(self):
        return self.post()

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('letter.guarantee') or 'New'
        lg = models.Model.create(self, vals)
        return lg


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    use_lg = fields.Boolean(string='LG Accounting', related='company_id.use_lg', readonly=False,
                            implied_group='Letter_Guarantee.use_lg')
    guarantee_journal_id = fields.Many2one(related='company_id.guarantee_journal_id', string='LG Account',
                                           readonly=False)


class ResCompany(models.Model):
    _inherit = 'res.company'

    use_lg = fields.Boolean(string="LG Accounting")
    guarantee_journal_id = fields.Many2one('account.account', string='LG Account')

    @api.constrains('use_lg')
    def onchange_lG_menu(self):
        if self.use_lg:
            lg_menu = self.env['res.groups'].search([('id', '=', self.env.ref('Letter_Guarantee.use_lg').id)])
            lg_menu.users = [(4, self.env.user.id)]
        else:
            lg_menu = self.env['res.groups'].search([('id', '=', self.env.ref('Letter_Guarantee.use_lg').id)])
            lg_menu.users = [(2, self.env.user.id)]
