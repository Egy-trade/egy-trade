# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    lg_credit_account_id = fields.Many2one('account.account', string='حساب خطاب الضمان الابتدائي ',)
    bank_credit_account_id = fields.Many2one('account.account', string='حساب المصاريف البنكية ',)
    tax_credit_account_id = fields.Many2one('account.account', string='حساب ضريبة',)
    lg_account_id = fields.Many2one('account.account', string='حساب تعهدات خطاب الضمان المدين ',)
    final_lg_account_id = fields.Many2one('account.account', string='حساب تعهدات خطاب الضمان الدائن ',)
    project_account_id = fields.Many2one('account.account', string='حساب تكلفة المشروع ',)
    final_account_id = fields.Many2one('account.account', string='حساب خطاب الضمان النهائي',)
    cover_percentage = fields.Float(string='Cover (%)', default=100.0)
    is_lg = fields.Boolean(string='Letter Of Guarantee')

    @api.onchange('is_lg')
    @api.constrains('is_lg')
    def unset_lg_accounts(self):
        for record in self:
            if not record.is_lg:
                record.lg_credit_account_id = False
                record.bank_credit_account_id = False
                record.tax_credit_account_id = False
                record.lg_account_id = False
                record.final_lg_account_id = False
                record.project_account_id = False
                record.final_account_id = False
                record.cover_percentage = False
