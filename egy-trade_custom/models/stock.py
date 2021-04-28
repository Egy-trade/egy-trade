# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import date, timedelta


class StockPickingStatusStage(models.Model):
    _name = "stock.picking.status.stage"
    _order = 'sequence'
    sequence = fields.Integer(string='Sequence')
    name = fields.Char(string='Name', required=True)
    duration = fields.Integer(string='Duration in Days', required=True)
    status_template_id = fields.Many2one('stock.picking.status.template', string='Template')


class StockPickingStatus(models.Model):
    _name = "stock.picking.status.template"

    name = fields.Char(string='Name', required=True)
    stage_ids = fields.One2many('stock.picking.status.stage', 'status_template_id', string='Stages', required=True)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    status_template_id = fields.Many2one('stock.picking.status.template',
                                         string='Route',
                                         tracking=True,
                                         domain="[('stage_ids' ,'!=', False)]",
                                         )
    status_stage = fields.Many2one('stock.picking.status.stage', string='Location', tracking=True)
    stage_change_date = fields.Date(string='Change Date')
    expected_date = fields.Date(string='Expected Date', readonly=True,
                                compute='_compute_status_stage')  # should fix this later on

    @api.depends('status_stage')
    def _compute_status_stage(self):
        for rec in self:
            rec.expected_date = rec.stage_change_date + timedelta(
                days=rec.status_stage.duration) if rec.stage_change_date else False

    # Need to improve this function
    @api.model
    def _transfer_status_change(self):
        today = date.today()
        stock_picking_ids = self.env['stock.picking'].search([('status_template_id', '!=', False),
                                                              ('state', 'not in', ['draft', 'cancel'])])
        users = self.env['res.users'].search([])
        mail_list = [u for u in users if u.has_group('egy-trade_custom.group_shipment_logistics')]
        for line in stock_picking_ids:
            if type(line.expected_date) != type(False):
                if line.expected_date >= today:
                    for u in mail_list:
                        # print(f'sending the notification to {u.partner_id.email_formatted}')
                        template_id = self.env.ref('egy-trade_custom.mail_template_transfer_status_alert').id
                        template = self.env['mail.template'].browse(template_id)
                        template['email_to'] = u.partner_id.email_formatted
                        template.send_mail(self.id, force_send=True)

    def action_confirm(self):
        result = super(StockPicking, self).action_confirm()
        if len(self.status_template_id.stage_ids):
            self.status_stage = self.status_template_id.stage_ids[0].id
            self.expected_date = self.stage_change_date + timedelta(
                days=rec.status_stage.duration) if self.stage_change_date else False
        return result
