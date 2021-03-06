# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import date, timedelta, datetime


class PartnerDocument(models.Model):
    _name = 'res.partner.document'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name')
    expires = fields.Boolean(string='Expires')
    expiration_date = fields.Date(string='Expiration Date')
    document = fields.Binary(string='Document')

    partner_id = fields.Many2one(string='Partner')

    @api.model
    def create(self, vals_list):
        partner_id = self._context['partner_id']
        vals_list['partner_id'] = partner_id
        res = super(PartnerDocument, self).create(vals_list)
        return res

    @api.onchange('expires')
    def _onchange_expires(self):
        self.expiration_date = False

    def _document_alert(self):
        users = self.env['res.users'].search([])
        mail_list = [u for u in users if u.has_group('egy-trade_custom.group_accounting_documents')]
        docs = self.search([])
        for doc in docs:
            if doc.expires and doc.expiration_date:
                if doc.expiration_date - timedelta(days=7) == date.today():
                    template_id = self.env.ref('egy-trade_custom.mail_template_document_reminder').id
                    template = self.env['mail.template'].browse(template_id)
                    for u in mail_list:
                        template['email_to'] = u.partner_id.email_formatted
                        template.send_mail(self.id, force_send=True)
                if doc.expiration_date == date.today():
                    template_id = self.env.ref('egy-trade_custom.mail_template_document_expired_reminder').id
                    template = self.env['mail.template'].browse(template_id)
                    for u in mail_list:
                        template['email_to'] = u.partner_id.email_formatted
                        template.send_mail(self.id, force_send=True)


class SupplierInfo(models.Model):
    _inherit = 'res.partner'

    delay = fields.Integer(string='Delivery Lead Time', default=1)
    documents = fields.One2many('res.partner.document', 'partner_id', string='Documents')

    def action_view_documents(self):
        # action = self.env.ref('egy-trade_custom.action_res_partner_documents')
        partner_id = self._context['partner_id']
        action = {
            'name': _('Partner Documents'),
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'res_model': 'res.partner.document',
            'domain': [('partner_id', '=', partner_id)],
        }
        return action

    @api.depends('documents')
    def _compute_document_count(self):
        for rec in self:
            rec.document_count = len(rec.documents)

    document_count = fields.Integer(string='Document Count', compute='_compute_document_count')
