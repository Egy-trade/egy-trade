# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from datetime import datetime


class AccountJournalInherit(models.Model):
    _inherit = 'account.journal'

    is_bank_journal = fields.Boolean(string='Is Check Bank journal')

    journal_type = fields.Selection([('payable', 'Notes Payable'), ('receivable', 'Notes Receivable')],
                                    string='Journal Type')


    journal_status = fields.Selection(
        [('rec_received', 'Customer Receive'), ('rec_deposit', 'Bank Deposit'),
         ('rec_refund', 'Bank Refund')],
        string='Receivable Journal Status')

    @api.onchange('journal_type')
    def reset_journal_status(self):
        for rec in self:
            if rec.journal_type == 'payable':
                rec.journal_status = False
