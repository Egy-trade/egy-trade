# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class LetterGuaranteeReport(models.Model):
    _name = 'letter.guarantee.report'

    start_date = fields.Date(string='Start Date', default=fields.Date.context_today, required=True, copy=False)
    end_date = fields.Date(string='End Date', default=fields.Date.context_today, copy=False)
    type = fields.Selection([
        ('initial', 'خطاب ضمان ابتدائي'),
        ('final', 'خطاب ضمان نهائي'),
    ], string='Type', default='initial')
    line_ids = fields.One2many('letter.guarantee.report.line', 'letter_id', )

    def action_print_lg_report(self):
        self.line_ids.unlink()
        cost = 0.0
        if self.type == 'initial':
            lg_list = self.env['initial.letter.guarantee'].search(
                [('type', '=', self.type), ('date_issue', '>=', self.start_date), ('date_issue', '<=', self.end_date)])
            if lg_list:
                for lg in lg_list:
                    self.env['letter.guarantee.report.line'].create({
                        'amount': lg.amount,
                        'bank_id': lg.journal_id.id,
                        'type': lg.type,
                        'currency_id': lg.currency_id.id,
                        'expire_date': lg.expire_date,
                        'date_issue': lg.date_issue,
                        'cost': lg.bank_amount,
                        'project': lg.project,
                        'name': lg.name,
                        'letter_id': self.id,
                    })
            return self.env.ref('letter_of_guarantee.report_lg').report_action(self)
        else:
            lg_list = self.env['final.letter.guarantee'].search(
                [('type', '=', self.type), ('date_issue', '>=', self.start_date), ('date_issue', '<=', self.end_date)])
            if lg_list:
                for lg in lg_list:
                    cost = lg.amount * (lg.bank_amount / 100)
                    self.env['letter.guarantee.report.line'].create({
                        'amount': lg.amount,
                        'bank_id': lg.journal_id.id,
                        'type': lg.type,
                        'currency_id': lg.currency_id.id,
                        'cost': cost,
                        'expire_date': lg.expire_date,
                        'date_issue': lg.date_issue,
                        'project': lg.project,
                        'name': lg.name,
                        'letter_id': self.id,
                    })
            return self.env.ref('letter_of_guarantee.report_lg').report_action(self)


class LetterGuaranteeReportLine(models.Model):
    _name = 'letter.guarantee.report.line'

    type = fields.Selection([
        ('initial', 'خطاب ضمان ابتدائي'),
        ('final', 'خطاب ضمان نهائي'),
    ], string='Type', default='initial')
    company_id = fields.Many2one('res.company', string='Company', readonly=True,
                                 default=lambda self: self.env.user.company_id)
    amount = fields.Monetary(currency_field='currency_id', string='Amount')
    bank_id = fields.Many2one('account.journal', string='Bank Name', domain=[('type', '=', 'bank')])
    letter_id = fields.Many2one('letter.guarantee.report')
    name = fields.Char('Name')
    project = fields.Char('Project Name')
    cost = fields.Monetary(currency_field='currency_id')
    date_issue = fields.Date('Issue Date')
    expire_date = fields.Date('Expiry Date')
    currency_id = fields.Many2one('res.currency', 'Currency')
    amount = fields.Monetary(currency_field='currency_id', string='Amount')
