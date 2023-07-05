# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class RequestLetterGuarantee(models.Model):
    _name = 'request.letter.guarantee'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    name = fields.Char('Request Number', default='New', readonly=True, track_visibility='onchange')
    state = fields.Selection([
        ('requested', 'Requested'),
        ('approved', 'Approved'),
        ('in_progress','In Progress'),
        ('closed', 'Closed'),
    ], string='Status', index=True, readonly=True, default='requested',
        track_visibility='onchange', copy=False)
    partner_id = fields.Many2one('res.partner', string='Customer', track_visibility='onchange', required=True)
    currency_id = fields.Many2one('res.currency', 'Currency',required=True)
    amount = fields.Monetary(currency_field='currency_id', string='Amount',required=True)
    reason = fields.Char('Reason', required=True)
    lg_id = fields.Many2one(comodel_name='letter.guarantee', string='LG Ref', readonly="1")

    def action_approve(self):
        if self.state == 'requested':
            self.state = 'approved'


    # @api.multi
    def action_create_lg(self):
        form_id = self.env.ref('Letter_Guarantee.wizard_letter_guarantee_view')
        return {
            # 'view_type': 'form',
            'view_mode': 'form',
            'views': [(form_id.id, 'form')],
            'res_model': 'letter.guarantee',
            'target': 'new',
            'type': 'ir.actions.act_window',
            'context': {'default_request_lg_id': self.id,
                        'default_currency_id': self.currency_id.id,
                        'default_partner_id':self.partner_id.id,
                        'default_amount': self.amount,
                       },
            'flags': {'tree': {'action_buttons': True}, 'form': {'action_buttons': True}, 'action_buttons': True},
        }

    def action_close(self):
        if self.state == 'in_progress':
            self.state = 'closed'
            self.lg_id.action_close()


    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('request.letter.guarantee') or 'New'
        lg_id1 = models.Model.create(self, vals)
        return lg_id1
