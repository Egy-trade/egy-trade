# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class InitialRequestLetterGuarantee(models.Model):
    _name = 'initial.request.letter.guarantee'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    name = fields.Char('Name', default='New', readonly=True, copy=False, track_visibility='onchange', )
    project = fields.Char('Project Name', track_visibility='onchange')
    company_id = fields.Many2one('res.company', string='Company', readonly=True
                                 , default=lambda self: self.env.user.company_id)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'VP Approval'),
        ('financial_Approve', 'Review'),
        ('reject', 'Rejected'),
        ('done', 'Done'),
    ], string='Status', index=True, readonly=True, default='draft',
        track_visibility='onchange', copy=False)
    partner_id = fields.Many2one('res.partner', string='Customer', track_visibility='onchange', required=True,
                                 )
    currency_id = fields.Many2one('res.currency', 'Currency', required=True, store=True, track_visibility='onchange',default=lambda self: self.env.user.company_id.currency_id)
    project_amount = fields.Monetary(currency_field='currency_id', string='Project Amount', required=True, store=True)
    amount = fields.Monetary(currency_field='currency_id', string='LG Amount', required=True, compute='_compute_amount')
    lg_percentage = fields.Float(string='LG (%)', required=True, store=True)
    reason = fields.Text('Reason')
    lg_id = fields.Many2one(comodel_name='letter.guarantee', string='LG Ref', readonly="1")
    login_user_id = fields.Many2one('res.users', string='Requested By', default=lambda self: self.env.user,
                                    readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', track_visibility='onchange')
    comment = fields.Text('Comment')

    def lg_reject(self):
        self.state = 'reject'

    def back_to_draft(self):
        self.state = 'draft'

    def get_initial_lg(self):
        return {
            'name': 'Letter Of Guarantee',
            # 'view_type': 'form',
            'domain': [('request_lg_id', '=', self.id)],
            'view_mode': 'tree,form',
            'res_model': 'initial.letter.guarantee',
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    # @api.multi
    @api.depends('project_amount', 'lg_percentage')
    def _compute_amount(self):
        for record in self:
            record.amount = record.project_amount * (record.lg_percentage / 100)

    @api.onchange('login_user_id')
    @api.constrains('login_user_id')
    def onchange_login_user_id(self):
        for record in self:
            employee_list = self.env['hr.employee'].search([('user_id', '=', record.login_user_id.id)])
            if employee_list:
                for employee in employee_list:
                    record.department_id = employee.department_id

    def action_approve(self):
        self.state = 'approved'

    def button_done(self):
        self.state = 'done'

    def button_financial_approve(self):
        self.state = 'financial_Approve'

    # @api.multi
    def action_create_lg(self):
        form_id = self.env.ref('letter_of_guarantee.initial_wizard_letter_guarantee_view')
        return {
            # 'view_type': 'form',
            'view_mode': 'form',
            'views': [(form_id.id, 'form')],
            'res_model': 'initial.letter.guarantee',
            'target': 'new',
            'type': 'ir.actions.act_window',
            'context': {'default_request_lg_id': self.id,
                        'default_currency_id': self.currency_id.id,
                        'default_partner_id': self.partner_id.id,
                        'default_amount': self.amount,
                        'default_project': self.project,
                        },
            'flags': {'tree': {'action_buttons': True}, 'form': {'action_buttons': True}, 'action_buttons': True},
        }

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('initial.request.letter.guarantee') or 'New'
        lg_id1 = models.Model.create(self, vals)
        return lg_id1
