# -*- coding: utf-8 -*-

##############################################################################
import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError , UserError

class CheckPaymentTransactionPayment(models.Model):

    _name = 'check.payment.transaction.payment'
    _description = 'Check Payment'
    _inherits = {'check.payment.transaction': 'check_payment_transaction_id'}

    check_payment_transaction_id = fields.Many2one('check.payment.transaction', required=True, string='Payment Reference', ondelete='cascade')
    account_payment_id = fields.Many2one('account.payment', readonly=True, string='Payment Reference', ondelete='cascade', index=True, states={'draft': [('readonly', False)]})


    def _compute_payment_type(self):
        for rec in self:
            if rec.account_payment_id:
                if rec.account_payment_id.payment_type == 'inbound':
                    rec.payment_type = rec.account_payment_id.payment_type
                elif rec.account_payment_id.payment_type == 'outbound':
                    rec.payment_type = rec.account_payment_id.payment_type
            else:
                rec.payment_type = 'inbound'

    @api.model
    def create(self, vals):
        
        if vals.get('account_payment_id', False):
            account_payment = self.env['account.payment'].browse(vals['account_payment_id'])
            vals['journal_id'] = account_payment.journal_id.id
            vals['partner_id'] = account_payment.partner_id.id
            vals['currency_id'] = account_payment.currency_id.id
            if account_payment.payment_type == 'inbound':
                vals['payment_type'] = 'inbound'
            elif account_payment.payment_type == 'outbound':
                vals['payment_type'] = 'outbound'
        
        res = super(CheckPaymentTransactionPayment, self).create(vals)
        
        return res

    def action_receive(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only a check with status draft can be received."))

            rec.name = rec.check_number
            print("rec === > ",rec)
            print("rec 222=== > ",rec.check_payment_transaction_id)
            if rec.check_payment_transaction_id:
                rec.check_payment_transaction_id.receive_date = fields.Date.today()
                rec.check_payment_transaction_id.rec_journal_id = rec.account_payment_id.journal_id.id
                rec.check_payment_transaction_id.action_receive()
                print("rec 33=== > ", rec)
            # rec.create_move_rec()
            rec.write({'state': 'received'})

    def action_issue(self):
        for rec in self:
            print("rec ==> ",rec)
            print("rec.check_issue_date ==> ",rec.check_issue_date)
            print("rec.check_payment_transaction_id.issue_date ==> ",rec.check_payment_transaction_id.issue_date)
            print("rec.check_payment_transaction_id ==> ",rec.check_payment_transaction_id)
            if rec.state != 'draft':
                raise UserError(_("Only a check with status draft can be issued."))

            rec.name =  rec.check_number
            rec.check_payment_transaction_id.issue_date = rec.check_issue_date
            rec.check_payment_transaction_id.action_issue()
            rec.write({'state': 'issued'})

    # @api.onchange('book_id', 'book_serial')
    # def onchange_book_id(self):
    #     self.check_number = self.book_serial.name or str(self.book_id.next_check_num)
    #     self.bank_id = self.book_id.bank_id.id

