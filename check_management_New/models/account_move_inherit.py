# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from datetime import datetime


class AccountMoveLineInherit(models.Model):
    _inherit = 'account.move.line'

    check_id = fields.Many2one(comodel_name='check.payment.transaction', string='Check')


class AccountMoveInherit(models.Model):
    _inherit = 'account.move'

    check_id = fields.Many2one(comodel_name='check.payment.transaction', ondelete='cascade', string='Check')
    journal_state = fields.Selection([('draft', 'Draft'),
                                      ('received', 'Received'),
                                      ('endorse', 'Endorse'),
                                      ('deposited', 'Deposited'),
                                      ('issued', 'Issued'),
                                      ('returned', 'Returned'),
                                      ('posted', 'Posted'),
                                      ('cancelled', 'Cancelled'),
                                      ('posted_issued', 'posted issued ')
                                      ],

                                     )
