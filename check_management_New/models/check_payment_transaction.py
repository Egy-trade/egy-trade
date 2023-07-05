# -*- coding: utf-8 -*-
##############################################################################
import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError, AccessError
import odoo.osv.osv

class CheckPaymentTransactionAbstract(models.AbstractModel):
    _name = "check.payment.transaction.abstract"
    _description = "Contains the logic shared between models which allows to register check payments"

    partner_id = fields.Many2one('res.partner', string='Partner', required=True)

    amount = fields.Monetary(string='Amount', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.user.company_id.currency_id)
    posted_date = fields.Date(string='Payment Date', required=False, copy=False)

    journal_id = fields.Many2one('account.journal', string='Journal',
                                 domain=[('type', 'in', ('bank', 'cash')), ('journal_type', '=', 'payable')])

    rec_journal_id = fields.Many2one('account.journal', string='Received Journal',
                                     domain=[('type', 'in', ('bank', 'cash'))])
    dep_journal_id = fields.Many2one('account.journal', string='Deposit Journal',
                                     domain=[('type', 'in', ('bank', 'cash')), ('journal_type', '=', 'receivable'),
                                             ('journal_status', '=', 'rec_deposit')])

    ref_journal_id = fields.Many2one('account.journal', string='Refund Journal',
                                     domain=[('type', 'in', ('bank', 'cash')), ('journal_type', '=', 'receivable'),
                                             ('journal_status', '=', 'rec_refund')])

    company_id = fields.Many2one('res.company', string='Company',default=lambda self: self.env.user.company_id.id, readonly=False)

    @api.onchange('rec_journal_id', 'journal_id')
    def get_company(self):
        for rec in self:
            if rec.journal_id:
                rec.company_id = rec.journal_id.company_id.id
            if rec.rec_journal_id:
                rec.company_id = rec.rec_journal_id.company_id.id

    @api.constrains('amount')
    def _check_amount(self):
        if self.amount < 0:
            raise ValidationError(_('The payment amount cannot be negative.'))


class CheckPaymentTransaction(models.Model):
    _name = 'check.payment.transaction'
    _inherit = ['mail.thread', 'check.payment.transaction.abstract']
    _description = 'Check Payment Transaction'
    _order = 'check_payment_date desc, check_name desc'

    def check_server_action(self,rec_ids,flag):
        context = dict(self._context) or {}
        context['default_check_ids'] = [(6, 0, rec_ids.ids)]
        context['default_name'] = flag
        return {
            'name':'Checks Server Action',
            'type':'ir.actions.act_window',
            'res_model':'action.check.wizard',
            'view_mode':'form',
            'view_id':self.env.ref('check_management_New.action_check_wizard_form_id').id,
            'context' : context,
            'target':'new',
        }




    state = fields.Selection([('draft', 'Draft'),
                              ('received', 'Received'),
                              ('endorse', 'Endorse'),
                              ('deposited', 'Deposited'),
                              ('issued', 'Issued'),
                              ('returned', 'Returned'),
                              ('posted', 'Posted'),
                              ('cancelled', 'Cancelled')
                              ],
                             required=True,
                             default='draft',
                             copy=False,
                             string="Status",
                             track_visibility='onchange'
                             )

    name = fields.Char(readonly=True, copy=False, default="Draft Check Payment");
    check_name = fields.Char('Notes', readonly=True, required=False, copy=True, states={'draft': [('readonly', False)]}, )
    check_number = fields.Char('Number', readonly=False, size=34, required=True, copy=True,)
    check_issue_date = fields.Date('Issue Date', readonly=True, copy=False, states={'draft': [('readonly', False)]},default=fields.Date.context_today)
    check_payment_date = fields.Date('Payment Date', copy=True,
                                     help="Only if this check is post dated")

    issue_date = fields.Date('Vendor Issue Date',readonly=True, copy=False, states={'draft': [('readonly', False)]},default=fields.Date.context_today)
    issue_refund_date = fields.Date('Vendor Refund Date')

    receive_date = fields.Date('Customer Receive Date')
    deposite_date = fields.Date('Bank Deposite Date')
    paid_date = fields.Date('Paid Date')
    receive_return_date = fields.Date('Customer Return Date')
    receive_refund_date = fields.Date('Bank Refund Date')

    amount = fields.Monetary(string='Amount', readonly=True, required=True, states={'draft': [('readonly', False)]})

    bank_journal_id = fields.Many2one('account.journal', string="Bank Journal", ondelete='restrict', copy=False,
                              domain=[('type', '=', 'bank'), ('is_bank_journal', '=', 'True')], required=False)
    bank_id = fields.Many2one("res.bank", string="Bank")


    destination_account_id = fields.Many2one('account.account', compute='_compute_destination_account_id',
                                             readonly=True)
    partner_bank = fields.Many2one(comodel_name="res.partner.bank", string="Partner Bank", required=False, )

    payment_type = fields.Selection(compute='_compute_payment_type',
                                    selection=[('outbound', 'Send Money'), ('inbound', 'Receive Money')], readonly=True,
                                    store=True, states={'draft': [('readonly', False)]})

    check_amount_in_words = fields.Char(string="Amount in Words",compute='_compute_amount_text')
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.user.company_id.currency_id)
    account_analytic_id= fields.Many2one('account.analytic.account', 'Analytic Account',)


    is_issue = fields.Boolean(string="is issue",  )

    check_type = fields.Selection(string="Check Position", selection=[('company', 'In company'), ('delayed', 'Delayed'),('consolidation', 'Consolidation'), ], required=False, )
    check_type_date = fields.Date(string="Date of procedure", required=False, )
    is_reviewed = fields.Boolean(string="Reviewed",  )
    ref = fields.Char(string="Reference",)
    partner_code = fields.Char(string="Partner Code",readonly=True)
    refund_customer = fields.Boolean(string="Refund Customer",  )
    position = fields.Char(string="Position", required=False, )
    journal_ids=fields.One2many('account.move','check_id',readonly=True)

    # book_id = fields.Many2one(comodel_name="check.book", string="Check Book", required=False, )
    # book_serial = fields.Many2one(comodel_name="check.book.line", string="Check Book Serail", required=False, )
    # serials_filter = fields.Many2many(comodel_name="check.book.line", string="All Available Serials", compute="compute_serials_filter" )
    # @api.depends('book_id')
    # def compute_serials_filter(self):
    #     for rec in self:
    #         if rec.book_id:
    #             serials = rec.book_id.serial_ids.filtered(lambda l: not l.reserved)
    #             print('serials ==> ',serials)
    #             rec.serials_filter = serials
    #         else:rec.serials_filter = False



    #
    # @api.onchange('book_id','book_serial')
    # def onchange_book_id(self):
    #     self.check_number =self.book_serial.name or str(self.book_id.next_check_num)
    #     self.bank_id = self.book_id.bank_id.id


    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.partner_code = self.partner_id.ref
        else:self.partner_code =False

    def action_reviewed(self):
        for rec in self:
            rec.is_reviewed = True


    @api.depends('amount','currency_id')
    def _compute_amount_text(self):
        self.check_amount_in_words = self.currency_id.amount_to_text(self.amount)

    def action_endorse(self):
            template = self.env.ref('check_management_New.endorse_check_wizard_form_id')
            return {
                'name': _("Endorse Check"),
                'type': 'ir.actions.act_window',
                'res_model': 'endorse.check.wizard',
                'view_mode': 'tree,form',
                'views': [[template.id, 'form']],
                'context': {'default_check_id': self.id},
                'target': 'new',
            }

    @api.model
    def create(self,vals):
        print("vals = ",vals)
        print(vals.get('check_payment_date'))
        type = vals.get('payment_type')
        if type =='inbound':
            vals['ref'] = self.env['ir.sequence'].next_by_code('check.received.code')
            r = self.env['calendar.event'].create({
                'name': vals.get('check_number')+':'+str(vals.get('check_name') or'' ),
                'description': self.env['ir.config_parameter'].sudo().get_param(
                    'check_notification.description_check_received'),
                'alarm_ids':[(6,0,self.env.company.reminder_ids.ids)],
                'partner_ids':[(6,0,[vals.get('partner_id'),self.env.user.partner_id.id])],
                # 'duration':0.5,
                'allday':True,
                'start':vals.get('check_payment_date') or fields.Datetime.now(),
                'stop':vals.get('check_payment_date')  or fields.Datetime.now(),

            })

        elif type == 'outbound':
            vals['ref'] = self.env['ir.sequence'].next_by_code('check.issue.code')
            r = self.env['calendar.event'].create({
                'name': vals.get('check_number')+':اشعار خاص بشيك رقم ',
                'description': self.env['ir.config_parameter'].sudo().get_param(
                    'check_notification.description_check_issued'),
                'alarm_ids': [(6, 0, self.env.company.reminder_ids.ids)],
                'partner_ids': [(6, 0, [vals.get('partner_id'), self.env.user.partner_id.id])],
                # 'duration': 0.5,
                'allday': True,
                'start': vals.get('check_payment_date') or fields.Datetime.now(),
                'stop': vals.get('check_payment_date') or fields.Datetime.now(),

            })
        rec = super(CheckPaymentTransaction, self).create(vals)

        return rec



    def button_journal_entries(self):
        return {
            'name': _('Journal Items'),
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('check_id', 'in', self.ids)],
        }



    def _compute_payment_type(self):
        for rec in self:
            rec.payment_type = 'inbound'

    def unlink(self):
        if any(rec.state != 'draft' for rec in self):
            raise UserError(_("You can not delete a check payment that is already posted"))
        return super(CheckPaymentTransaction, self).unlink()

    def action_receive(self):
        self.reset_before_add('received')
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only a check with status draft can be received."))

            if rec.amount == 0.00:
                raise ValidationError(_("Check amount must be more than 0."))
            # edit_move = rec.env['account.move'].search([('check_id', '=', rec.id)])

            # for line in edit_move:
            #     print(tuple(line.line_ids.ids))
            #     if tuple(line.line_ids.ids):
            #         rec.env.cr.execute("DELETE FROM account_move_line WHERE id in %s " % (tuple(line.line_ids.ids),))

            rec.name = rec.check_number
            rec.create_move_rec()
            print("**** action_receive *****")
            rec.write({'state': 'received'})




    @api.constrains('check_number','bank_journal_id')
    def _check_method_name(self):
        if self.check_number:
            res = self.search([('id','!=',self.id),('check_number','=',self.check_number),('bank_journal_id','=',self.bank_journal_id.id),('state','not in',['endorse','cancelled','draft'])])
            print(res)
            if res:
                raise UserError('The check Number Must be UNIQUE!')

    def action_deposit(self):
        self.reset_before_add('deposited')
        for rec in self:
            if rec.state not in ['received','returned']:
                raise UserError(_("Only a validated check can be deposited."))
            if not rec.dep_journal_id:
                raise ValidationError(_("Please choose Deposit Journal."))
            if not rec.deposite_date:
                raise ValidationError(_("Please choose Deposit Date."))
            if not rec.bank_journal_id:
                raise ValidationError(_("Please choose Bank Journal"))
            rec.create_move_dep()
            if self.refund_customer:
                self.refund_customer=False
            rec.write({'state': 'deposited'})

    def action_fund_credited(self):
        self.reset_before_add('posted')
        for rec in self:
            if rec.state != 'deposited':
                raise UserError(_("Only a check already deposited to bank can be posted."))
            if not rec.paid_date:
                raise UserError(_("Please Choose Paid Date."))
            rec.create_move_coll()
            rec.write({'state': 'posted'})

    def action_return_received_check(self):
        for rec in self:
            if rec.state != 'deposited':
                raise UserError(_("Only a check already deposited to bank can be returned."))

            # if not rec.ret_journal_id:
            #     raise ValidationError(_("Please choose Return Journal."))
            if not rec.ref_journal_id:
                raise ValidationError(_("Please choose Refund Journal."))
            if not rec.receive_refund_date:
                raise ValidationError(_("Please choose Refund Date."))
            # if not rec.receive_return_date:
            #     raise ValidationError(_("Please choose Return Date."))
            rec.create_move_ref()
            # rec.create_move_ret()
            rec.refund_customer =True

            rec.write({'state': 'returned'})

    def action_return_received_check2(self):
        for rec in self:
            if rec.state not in ['deposited','returned']:
                raise UserError(_("Only a check already deposited to bank can be returned."))

            # if not rec.ret_journal_id:
            #     raise ValidationError(_("Please choose Return Journal."))
            # if not rec.ref_journal_id:
            #     raise ValidationError(_("Please choose Refund Journal."))
            # if not rec.receive_refund_date:
            #     raise ValidationError(_("Please choose Refund Date."))
            if not rec.receive_return_date:
                raise ValidationError(_("Please choose Return Date."))
            # rec.create_move_ref()
            rec.create_move_ret()
            rec.refund_customer =False
            rec.write({'state': 'returned'})

    def action_cancel(self):
        for rec in self:
            # if rec.state != 'received':
            #     raise UserError(_("You cannot cancel check at this time."))
            self.create_move_cancel()
            rec.write({'state': 'cancelled'})

    def rest_draft(self):
        print(self)
        for rec in self:
            if rec.refund_customer:
                raise UserError(_("You can not do rest to draft before returned Customer Checks"))

            print(rec)
            rec.refund_customer = False
            rec.write({'state': 'draft'})

    def reset_draft(self):
        jornal_i=self.env['account.move'].search([('check_id','=',self.id)])
        # jornal_item = self.env['account.move.line'].search([('check_id', '=', self.id)])
        # print(jornal_i)
        # print(jornal_item)
        # for item in jornal_item:
        #     item.write({'parent_state': 'draft'})
        for rec in jornal_i:
            rec.button_draft()
            print(tuple(rec.line_ids.ids))
            if tuple(rec.line_ids.ids):
                rec.env.cr.execute("DELETE FROM account_move_line WHERE id in %s " %(tuple(rec.line_ids.ids),))
            else:
                self.make_messege()

        self.state='draft'

    def reset_before_add(self,state):
        journal_type = self.env['account.move'].search([('check_id', '=', self.id),('journal_state','=',state)])
        for rec in journal_type:
            rec.button_draft()
            print(tuple(rec.line_ids.ids))
            if tuple(rec.line_ids.ids):
                rec.env.cr.execute("DELETE FROM account_move_line WHERE id in %s " % (tuple(rec.line_ids.ids),))
            else:
                self.make_messege()


    def create_move_cancel(self):
        self.ensure_one()
        edit_move = self.env['account.move'].search([('check_id', '=', self.id)])
        for rec in edit_move:
            rec.button_cancel()

        # move = self.env["account.move"].create(
        #     self._prepare_move_data_cancel())
        # move.action_post()
        # return move

    def _prepare_move_data_cancel(self):
        self.ensure_one()
        journal = self.rec_journal_id.id
        check_name = self.check_name or ''
        return {
            "check_id": self.id,
            "journal_id": journal,
            "date": fields.Date.today(),
            "ref": "Canceled " + self.check_number +' '+ check_name ,
            "line_ids": self._prepare_move_line_data_cancel(),
        }

    def _prepare_move_line_data_cancel(self):
        self.ensure_one()
        if self.partner_id:
            partner = self.partner_id
        journal = self.rec_journal_id
        print('partner', partner)
        print('self.company_id.currency_id', self.company_id.currency_id)
        print('self.currency_id', self.currency_id)
        company_currency = self.env.user.company_id.currency_id
        if company_currency != self.currency_id:
            amount = self.currency_id.compute(self.amount, company_currency, round=False)
            amount_currency = self.amount
        else:
            amount = self.amount
            amount_currency = 0
        result = []
        print("**** j", journal.default_account_id)
        print("**** j", self.partner_id.property_account_receivable_id.id,)
        result.append((0, 0, {
            "name": self.check_number,
            "account_id": self.partner_id.property_account_receivable_id.id,
            "currency_id": self.currency_id.id,
            "amount_currency": amount_currency,
            ## "analytic_account_id": self.account_analytic_id.id,

            "debit": amount,
            "credit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.receive_date,
            "date": fields.Date.today(),
            "check_id": self.id
        }))
        result.append((0, 0, {
            "name": 'Customer Payment',
            "account_id": journal.default_account_id.id,
            "credit": amount,
            ## "analytic_account_id": self.account_analytic_id.id,

            "amount_currency": amount_currency * -1,
            "currency_id": self.currency_id.id,
            "debit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.receive_date,
            "date": fields.Date.today(),
            "check_id": self.id
        }))
        return result

    def action_cancel_issue(self):
        for rec in self:
            # if rec.state != 'draft':
            #     raise UserError(_("Only a check with status draft can be Cancelled."))
            rec.create_move_cancel()
            rec.write({'state': 'cancelled'})
    def action_issue(self):
        self.reset_before_add('issued')

        for rec in self:

            if rec.state != 'draft':
                raise UserError(_("Only a check with status draft can be issued."))
            if rec.amount == 0.00:
                raise ValidationError(_("Check amount must be more than 0."))

            rec.name = rec.check_number
            rec.create_move()
            rec.write({'state': 'issued'})

    def action_fund_debited(self):
        self.reset_before_add('posted_issued')

        for rec in self:
            print("************ ", rec)
            if rec.check_payment_date and rec.check_payment_date > fields.Date.today():
                raise UserError(_("Can not issued this check until now"))
            if rec.state != 'issued':
                raise UserError(_("Only a issued check can be posted."))
            if not rec.bank_journal_id:
                raise UserError(_("Please select Bank !."))
            if not rec.check_payment_date:
                raise ValidationError(_("Please choose Payment Date."))
            rec.create_move_delivered()
            rec.write({'state': 'posted'})

    def action_return_issued_check(self):
        for rec in self:
            if rec.state != 'issued':
                raise UserError(_("Only a issued check can be returned."))
            if not rec.issue_refund_date:
                raise UserError(_("Please choose Refund Date."))
            rec.create_move_reversed()
            rec.write({'state': 'returned'})

    # /////////////////////////////////////////////////////////////////////////////////////////

    # ************************ Send (Issued) Checks Functions *******************************

    def create_move(self):
        self.ensure_one()
        if not self.issue_date:
            raise UserError(_("Please choose Vendor Issue Date."))

        edit_move = self.env['account.move'].search([('check_id', '=', self.id), ('journal_state', '=', 'issued')])

        if edit_move:
            edit_move.write(self._prepare_move_data())
            edit_move.action_post()
            return edit_move
        else:
            move = self.env["account.move"].create(
                self._prepare_move_data())
            move.action_post()
            return move

    def create_move_reversed(self):
        self.ensure_one()
        move = self.env["account.move"].create(
            self._prepare_move_data_reversed())
        move.action_post()
        return move

    def create_move_delivered(self):
        self.ensure_one()

        edit_move = self.env['account.move'].search([('check_id', '=', self.id), ('journal_state', '=', 'posted_issued')])

        if edit_move:
            edit_move.write(self._prepare_move_data_delivered())
            edit_move.action_post()
            return edit_move
        else:
            move = self.env["account.move"].create(
                self._prepare_move_data_delivered())
            move.action_post()
            return move

    def _prepare_move_data(self):
        self.ensure_one()
        check_name = self.check_name or ''
        return {
            "check_id": self.id,
            "journal_id": self.journal_id.id,
            "date": self.issue_date,
            "ref": self.check_number +' '+ check_name ,
            "journal_state": 'issued',
            "line_ids": self._prepare_move_line_data(),
        }

    def _prepare_move_data_reversed(self):
        self.ensure_one()

        aml = self.env['account.move.line'].search(
            [('check_id', '=', self.id), ('credit', '>', 0), ('move_id.ref', 'not ilike', 'reversal of:'),
             ('account_id', '=', self.journal_id.default_account_id.id)], order='id desc')

        return {
            "check_id": self.id,
            "journal_id": self.journal_id.id,
            "date": self.check_payment_date,
            "ref": (_('Reversal of: %s')) % (aml[0].move_id.name),
            "line_ids": self._prepare_move_line_data_reversed(),
        }

    def _prepare_move_data_delivered(self):
        self.ensure_one()
        check_name = self.check_name or ''
        return {
            "check_id": self.id,
            "journal_id": self.journal_id.id,
            "date": self.check_payment_date,
            "ref": self.check_number +' '+check_name ,
            "journal_state": 'posted_issued',
            "line_ids": self._prepare_move_line_data_delivered(),
        }

    def _prepare_move_line_data(self):
        self.ensure_one()
        if self.partner_id:
            partner = self.partner_id
        result = []
        company_currency = self.env.user.company_id.currency_id
        if company_currency != self.currency_id:
            amount = self.currency_id.compute(self.amount, company_currency, round=False)
            amount_currency = self.amount
        else:
            amount = self.amount
            amount_currency = 0
        result.append((0, 0, {
            "name": 'Vendor Payment',
            "account_id": self.partner_id.property_account_payable_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,

            "debit": amount,
            "amount_currency": amount_currency,
            "credit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.issue_date,
            "date": self.issue_date,
            "check_id": self.id
        }))
        result.append((0, 0, {
            "name": self.check_number,
            "account_id": self.journal_id.default_account_id.id,
           ## "analytic_account_id": self.account_analytic_id.id,

            "currency_id": self.currency_id.id,
            "credit": amount,
            "amount_currency": amount_currency * -1,
            "debit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.issue_date,
            "date": self.issue_date,
            "check_id": self.id
        }))
        return result

    def _prepare_move_line_data_reversed(self):

        self.ensure_one()
        if self.partner_id:
            partner = self.partner_id
        result = []
        company_currency = self.env.user.company_id.currency_id
        if company_currency != self.currency_id:
            amount = self.currency_id.compute(self.amount, company_currency, round=False)
            amount_currency = self.amount
        else:
            amount = self.amount
            amount_currency = 0
        result.append((0, 0, {
            "name": self.check_number,
            "account_id": self.journal_id.default_account_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,

            "debit": amount,
            "amount_currency": amount_currency,
            "credit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.issue_refund_date,
            "date": self.issue_refund_date,
            "check_id": self.id
        }))
        result.append((0, 0, {
            "name": 'Vendor Payment',
            "account_id": self.partner_id.property_account_payable_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,

            "credit": amount,
            "amount_currency": amount * -1 ,
            "debit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.issue_refund_date,
            "date": self.issue_refund_date,
            "check_id": self.id
        }))
        return result

    def _prepare_move_line_data_delivered(self):
        self.ensure_one()
        if self.partner_id:
            partner = self.partner_id
        result = []
        company_currency = self.env.user.company_id.currency_id
        if company_currency != self.currency_id:
            amount = self.currency_id.compute(self.amount, company_currency, round=False)
            amount_currency = self.amount
        else:
            amount = self.amount
            amount_currency = 0
        result.append((0, 0, {
            "name": self.check_number,
            "account_id": self.journal_id.default_account_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,

            "debit": amount,
            "amount_currency": amount_currency,
            "credit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.check_payment_date,
            "date": self.check_payment_date,
            "check_id": self.id,
        }))
        result.append((0, 0, {
            "name": self.bank_journal_id.name + ' Bank Withdrawal',
            "account_id": self.bank_journal_id.default_account_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,

            "credit": amount,
            "amount_currency": amount_currency,
            "debit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.check_payment_date,
            "date": self.check_payment_date,
            "check_id": self.id,
        }))
        return result



    def create_move_rec(self):
        self.ensure_one()
        if not self.receive_date:
            raise ValidationError(_("Please choose Customer Receive Date."))

        edit_move = self.env['account.move'].search([('check_id', '=', self.id),('journal_state','=','received')])

        if edit_move:
            edit_move.write(self._prepare_move_data_rec())
            edit_move.action_post()
            return edit_move
        else:
            move = self.env["account.move"].create(
                self._prepare_move_data_rec())
            move.action_post()
            return move

    def _prepare_move_data_rec(self):
        self.ensure_one()
        journal = self.rec_journal_id.id
        check_name = self.check_name or ''
        return {
            "check_id": self.id,
            "journal_id": journal,
            "date": self.receive_date,
            "ref":  self.check_number +' '+ check_name,
            "journal_state":  'received',
            "line_ids": self._prepare_move_line_data_rec(),
        }

    def _prepare_move_line_data_rec(self):
        self.ensure_one()
        if self.partner_id:
            partner = self.partner_id
        journal = self.rec_journal_id
        print('partner',partner)
        print('self.company_id.currency_id',self.company_id.currency_id)
        print('self.currency_id',self.currency_id)
        company_currency = self.env.user.company_id.currency_id
        if company_currency != self.currency_id:
            amount = self.currency_id.compute(self.amount, company_currency, round=False)
            amount_currency = self.amount
        else:
            amount = self.amount
            amount_currency =0
        result = []
        print("**** j",journal.default_account_id)
        print("**** j",self.partner_id.property_account_receivable_id.id,)
        result.append((0, 0, {
            "name":  self.check_number,
            "account_id": journal.default_account_id.id,
            "currency_id": self.currency_id.id,
            "amount_currency": amount_currency,
           # "analytic_account_id": self.account_analytic_id.id,

            "debit": amount,
            "credit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.receive_date,
            "date": self.receive_date,
            "check_id": self.id
        }))
        result.append((0, 0, {
            "name": 'Customer Payment',
            "account_id": self.partner_id.property_account_receivable_id.id,
           # "analytic_account_id": self.account_analytic_id.id,

            "credit": amount,
            "amount_currency": amount_currency *-1,
            "currency_id": self.currency_id.id,
            "debit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.receive_date,
            "date": self.receive_date,
            "check_id": self.id
        }))
        return result

    def create_move_dep(self):
        self.ensure_one()
        edit_move = self.env['account.move'].search([('check_id', '=', self.id), ('journal_state', '=', 'deposited')])

        if edit_move:
            edit_move.write(self._prepare_move_data_dep())
            edit_move.action_post()
            return edit_move
        else:
            move = self.env["account.move"].create(
                self._prepare_move_data_dep())
            move.action_post()

            return move

    def _prepare_move_data_dep(self):
        self.ensure_one()
        journal = self.dep_journal_id.id
        check_name = self.check_name or ''
        return {
            "check_id": self.id,
            "journal_id": journal,
            "date": self.deposite_date,
            "ref": self.check_number +' '+ check_name ,
            "journal_state": 'deposited',
            "line_ids": self._prepare_move_line_data_dep(),
        }

    def _prepare_move_line_data_dep(self):
        self.ensure_one()
        if self.partner_id:
            partner = self.partner_id
        journal = self.dep_journal_id
        result = []
        company_currency = self.env.user.company_id.currency_id
        if company_currency != self.currency_id:
            amount = self.currency_id.compute(self.amount, company_currency, round=False)
            amount_currency = self.amount
        else:
            amount = self.amount
            amount_currency = 0
        result.append((0, 0, {
            "name":  self.check_number,
            "account_id": journal.default_account_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,

            "debit": amount,
            "amount_currency": amount_currency,
            "credit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.deposite_date,
            "date": self.deposite_date,
            "check_id": self.id
        }))
        result.append((0, 0, {
            "name": self.check_number,
            "account_id": self.rec_journal_id.default_account_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,

            "credit": amount,
            "amount_currency": amount_currency *-1,
            "debit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.deposite_date,
            "date":self.deposite_date,
            "check_id": self.id
        }))
        return result

    def create_move_coll(self):
        self.ensure_one()
        edit_move = self.env['account.move'].search([('check_id', '=', self.id), ('journal_state', '=', 'posted')])
        if edit_move:
            edit_move.write(self._prepare_move_data_coll())
            edit_move.action_post()
            return edit_move
        else:
            move = self.env["account.move"].create(
                self._prepare_move_data_coll())
            move.action_post()
            return move

    def _prepare_move_data_coll(self):
        self.ensure_one()
        journal = self.bank_journal_id.id
        check_name = self.check_name or ''
        return {
            "check_id": self.id,
            "journal_id": journal,
            "date": self.paid_date,
            "ref": self.check_number +' '+ check_name ,
            "journal_state": 'posted',
            "line_ids": self._prepare_move_line_data_coll(),
        }

    def _prepare_move_line_data_coll(self):
        self.ensure_one()
        if self.partner_id:
            partner = self.partner_id
        journal = self.bank_journal_id
        result = []
        company_currency = self.env.user.company_id.currency_id
        if company_currency != self.currency_id:
            amount = self.currency_id.compute(self.amount, company_currency, round=False)
            amount_currency = self.amount
        else:
            amount = self.amount
            amount_currency = 0
        result.append((0, 0, {
            "name": journal.name + ' Bank Collection',
            "account_id": journal.default_account_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,

            "debit": amount,
            "amount_currency": amount_currency,
            "credit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.paid_date,
            "date": self.paid_date,
            "check_id": self.id
        }))
        result.append((0, 0, {
            "name": self.check_number,
            "account_id": self.dep_journal_id.default_account_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,

            "credit": amount,
            "amount_currency": amount_currency * -1,
            "debit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.paid_date,
            "date": self.paid_date,
            "check_id": self.id
        }))
        return result

    def create_move_ref(self):
        self.ensure_one()
        move = self.env["account.move"].create(
            self._prepare_move_data_ref())
        move.action_post()
        return move

    def _prepare_move_data_ref(self):
        self.ensure_one()

        aml = self.env['account.move.line'].search(
            [('check_id', '=', self.id), ('credit', '>', 0), ('move_id.ref', 'not ilike', 'reversal of:'),
             ('account_id', '=', self.rec_journal_id.default_account_id.id)], order='id desc')

        return {
            "check_id": self.id,
            "journal_id": self.ref_journal_id.id,
            "date": self.receive_refund_date,
            "ref": (_('Reversal of: %s')) % (aml[0].move_id.name),
            "line_ids": self._prepare_move_line_data_ref(),
        }

    def _prepare_move_line_data_ref(self):

        self.ensure_one()
        if self.partner_id:
            partner = self.partner_id
        journal = self.ref_journal_id
        result = []
        company_currency = self.env.user.company_id.currency_id
        if company_currency != self.currency_id:
            amount = self.currency_id.compute(self.amount, company_currency, round=False)
            amount_currency = self.amount
        else:
            amount = self.amount
            amount_currency = 0
        result.append((0, 0, {
            "name": self.check_number,
            "account_id": journal.default_account_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,

            "debit": amount,
            "amount_currency": amount_currency,
            "credit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.receive_refund_date,
            "date": self.receive_refund_date,
            "check_id": self.id
        }))
        result.append((0, 0, {
            "name": self.check_number,
            "account_id": self.dep_journal_id.default_account_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,

            "credit": amount,
            "amount_currency": amount_currency *-1,
            "debit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.receive_refund_date,
            "date": self.receive_refund_date,
            "check_id": self.id
        }))
        return result

    def create_move_ret(self):
        self.ensure_one()
        move = self.env["account.move"].create(
            self._prepare_move_data_ret())
        move.action_post()
        return move

    def _prepare_move_data_ret(self):
        self.ensure_one()

        aml = self.env['account.move.line'].search(
            [('check_id', '=', self.id), ('credit', '>', 0), ('move_id.ref', 'not ilike', 'reversal of:'),
             ('account_id', '=', self.partner_id.property_account_receivable_id.id)], order='id desc')

        return {
            "check_id": self.id,
            "journal_id": self.ref_journal_id.id,
            "date": self.receive_return_date,
            "ref": (_('Reversal of: %s')) % (aml[0].move_id.name),
            "line_ids": self._prepare_move_line_data_ret(),
        }

    def _prepare_move_line_data_ret(self):
        self.ensure_one()
        if self.partner_id:
            partner = self.partner_id
        journal = self.ref_journal_id
        result = []
        company_currency = self.env.user.company_id.currency_id
        if company_currency != self.currency_id:
            amount = self.currency_id.compute(self.amount, company_currency, round=False)
            amount_currency = self.amount
        else:
            amount = self.amount
            amount_currency = 0
        result.append((0, 0, {
            "name": self.check_number,
            "account_id": self.partner_id.property_account_receivable_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,
            "debit": amount,
            "amount_currency": amount_currency,
            "credit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.receive_return_date,
            "date": self.receive_return_date,
            "check_id": self.id
        }))
        result.append((0, 0, {
            "name": self.check_number,
            "account_id": journal.default_account_id.id,
            "currency_id": self.currency_id.id,
           # "analytic_account_id": self.account_analytic_id.id,
            "credit": amount,
            "amount_currency": amount_currency * -1,
            "debit": 0.0,
            "partner_id": partner.id,
            "date_maturity": self.receive_return_date,
            "date": self.receive_return_date,
            "check_id": self.id
        }))
        return result

    def make_messege(self):
        print('----------------------')
        print('----------------------')
        notification = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('RESET TO DRAFT'),
                'message': 'Already Check in Draft State ',
                'sticky': True,
            }
        }
        return notification




    def make_notification(self):
        c= self.env['ir.config_parameter'].sudo().get_param('check_notification.description_check_received') or 'default_email@mail.com'
        d= self.env['ir.config_parameter'].sudo().get_param('check_notification.description_check_issued') or 'default_email@mail.com'
        # d= self.env['res.company'].get_param('check_notification.description_check_issued') or 'default_email@mail.com'
        # print(self.env.company.reminder_ids.ids)
        # print(self.env.user.partner_id.id)
        print(c)
        print(d)
        print(fields.datetime.now())
        # edit_move = self.env['account.move'].search([('check_id', '=', self.id)])
        # print(edit_move, '-----')

        # return {
        #     'res_model': 'calendar.event',
        #     'type': 'ir.actions.act_window',
        #     'view_mode': 'form',
        #     'view_type': 'form',
        #     'view_id': self.env.ref('calendar.view_calendar_event_form').id,
        #     'target': 'self',
        #     'context': {'default_name': self.ref +' :اشعار خاص بشيك رقم','default_start': self.receive_date or self.issue_date,'default_duration':0.5,'default_partner_ids': [self.partner_id.id,]}
        # }