# © 2016 Serpent Consulting Services Pvt. Ltd. (support@serpentcs.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
from lxml import etree

from odoo import tools
from odoo import api, models,fields,exceptions,_


class ActionWizard(models.TransientModel):
    _name = 'action.check.wizard'

    check_ids = fields.Many2many(comodel_name='check.payment.transaction', string='Checks#', readonly=True)
    date = fields.Date(string="", required=True, )
    name = fields.Char(string="", required=False,readonly=True )

    def action_close(self):
        print('check_ids ==>> ',self.check_ids)
        print('name ==>> ',self.name)
        print('date ==>> ',self.date)
        for rec in self.check_ids:
            if self.name=='receive':
                rec.receive_date= self.date
                rec.action_receive()
            if self.name == 'issue':
                rec.issue_date =self.date
                rec.action_issue()
            if self.name == 'done_issue':
                rec.check_payment_date = self.date
                rec.action_fund_debited()
            if self.name == 'bank_deposit':
                rec.deposite_date = self.date
                rec.action_deposit()
            if self.name == 'make_done':
                rec.paid_date = self.date
                rec.action_fund_credited()






