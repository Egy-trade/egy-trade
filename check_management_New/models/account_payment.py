# -*- coding: utf-8 -*-
##############################################################################

import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, AccessError, UserError


class AccountRegisterPayments(models.TransientModel):
    _inherit = "account.payment.register"

    hide_check_payment = fields.Boolean(compute='_compute_hide_check_payment',
                                        help="Technical field used to hide the check_payment if the selected journal has not been set or the selected journal has a type neither in in bank nor cash")

    check_payment_transaction_ids = fields.Many2many('check.payment.transaction.payment', string="Check Information",)

    def _create_payment_vals_from_wizard(self, batch_result):
        print("*** check_payment_transaction_ids ***")
        payment = super(AccountRegisterPayments, self)._create_payment_vals_from_wizard(batch_result)
        payment['check_payment_transaction_ids'] =[(6,0,self.check_payment_transaction_ids.ids)]
        return payment

    @api.depends('journal_id')
    def _compute_hide_check_payment(self):
        for payment in self:

            if not payment.journal_id:
                payment.hide_check_payment = True
                continue
            if payment.journal_id.type == 'bank' or payment.journal_id.type == 'cash':
                payment.hide_check_payment = False
            else:
                payment.hide_check_payment = True


class AccountPayment(models.Model):
    _inherit = 'account.payment'
    mount_text = fields.Char(string="Amount Text", compute="_compute_amount_text")
    currency_id = fields.Many2one(
        groups=''
    )

    @api.depends('amount', 'currency_id')
    def _compute_amount_text(self):
        print("hhhh ===> ", self)
        for rec in self:
            if rec.currency_id:
                rec.mount_text = rec.currency_id.amount_to_text(rec.amount)
            else:
                rec.mount_text = ''

    hide_check_payment = fields.Boolean(compute='_compute_hide_check_payment',
        help="Technical field used to hide the check_payment if the selected journal has not been set or the selected journal has a type neither in in bank nor cash")

    check_payment_transaction_ids = fields.One2many('check.payment.transaction.payment', 'account_payment_id', string="Check Information",
        readonly=True, states={'draft': [('readonly', False)]}, copy=False)

    def print_cash_payment(self):
        return self.env.ref('check_management_New.action_print_cash_report').report_action(self)

    def print_checks(self):
        return self.env.ref('check_management_New.check_folder_report').report_action(self)

    def write(self, vals):
        
        for rec in self:
            if 'journal_id' in vals:
                for check_payment in rec.check_payment_transaction_ids:
                    check_payment.journal_id = vals['journal_id']
            if 'partner_id' in vals:
                for check_payment in rec.check_payment_transaction_ids:
                    check_payment.partner_id = vals['partner_id']
            if 'currency_id' in vals:
                for check_payment in rec.check_payment_transaction_ids:
                    check_payment.currency_id = vals['currency_id']
            if 'payment_type' in vals:
                for check_payment in rec.check_payment_transaction_ids:
                    if vals['payment_type'] == 'inbound':
                        check_payment.payment_type = 'inbound'
                    elif vals['payment_type'] == 'outbound':
                        check_payment.payment_type = 'outbound'
        res = super(AccountPayment, self).write(vals)
        
        return res


    @api.onchange('check_payment_transaction_ids')
    def _onchange_check_payment_transaction_ids(self):
        if self.check_payment_transaction_ids:
            total = 0.0
            for line in self.check_payment_transaction_ids:
                total += line.amount
            self.amount = total
            print("total == ",total)

    @api.onchange('check_payment_transaction_ids')
    def _onchange_check_payment_transaction_ids(self):
        if self.check_payment_transaction_ids:
            total = 0.0
            for line in self.check_payment_transaction_ids:
                total += line.amount
            self.amount = total

 

    @api.onchange('payment_type')
    def _onchange_payment_type(self):
        # res = super(AccountPayment, self)._onchange_payment_type()
        if self.payment_type == 'transfer':
            self.hide_check_payment = True
        elif self.payment_type == 'outbound' or self.payment_type == 'inbound':
            if self.journal_id.type == 'bank' or self.journal_id.type == 'cash':
                self.hide_check_payment = False
            else:
                self.hide_check_payment = True
        #res['domain']['payment_type'] = self.payment_type

    @api.onchange('journal_id')
    def _onchange_journal(self):
        # res = super(AccountPayment, self)._onchange_journal()
        if self.journal_id:
            if self.check_payment_transaction_ids:
                for rec in self.check_payment_transaction_ids:
                    rec.journal_id = self.journal_id
        # return res

    @api.depends('journal_id')
    def _compute_hide_check_payment(self):
        for payment in self:
            if payment.payment_type == 'transfer':
                payment.hide_check_payment = True
                continue
            if not payment.journal_id:
                payment.hide_check_payment = True
                continue
            if payment.payment_type == 'outbound' or payment.payment_type == 'inbound':
                if payment.journal_id.type == 'bank' or payment.journal_id.type == 'cash':
                    payment.hide_check_payment = False
                else:
                    payment.hide_check_payment = True
