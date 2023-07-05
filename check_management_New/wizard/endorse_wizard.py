# © 2016 Serpent Consulting Services Pvt. Ltd. (support@serpentcs.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
from lxml import etree

from odoo import tools
from odoo import api, models,fields,exceptions,_


class EndorseWizard(models.TransientModel):
    _name = 'endorse.check.wizard'

    check_id = fields.Many2one('check.payment.transaction', 'Endorse Check#', readonly=True)
    partner_id = fields.Many2one(comodel_name="res.partner", string="Vendor")



    def action_close(self):
        self.check_id.state = 'endorse'
        check = self.env['check.payment.transaction'].create({
            'state': 'draft',
            'bank_journal_id': self.check_id.bank_journal_id.id,
            'journal_id': self.check_id.journal_id.id,
            'partner_id': self.partner_id.id,
            'name': 'Endorse From check#' + self.check_id.check_number,
            'check_name': 'Endorse From check#' + self.check_id.name,
            'amount': self.check_id.amount,
            'check_issue_date': fields.Date.today(),
            'check_number': self.check_id.check_number,
            'payment_type': 'outbound',
            'check_payment_date': fields.Date.today(),
            'issue_date': fields.Date.today(),

        })

        tree_view_id = self.env.ref('check_management_New.check_payment_vendor_list').id
        form_view_id = self.env.ref('check_management_New.check_payment_form_statusbar_vendor').id

        return {
            'name': _('Checks'),
            'res_model': 'check.payment.transaction',
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'views': [(tree_view_id, 'tree'), (form_view_id, 'form')],
            'target': 'current',
            'nodestroy': True,
            'domain': [('id', 'in', check.ids)],
        }







