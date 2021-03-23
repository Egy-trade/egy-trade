# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import date, timedelta


class StockPickingStatusStage(models.Model):
    _name = "stock.picking.status.stage"
    _order = 'sequence'
    sequence = fields.Integer(string='Sequence')
    name = fields.Char(string='Name', required=True)
    duration = fields.Integer(string='Duration', required=True)
    status_template_id = fields.Many2one('stock.picking.status.template', string='Template')


class StockPickingStatus(models.Model):
    _name = "stock.picking.status.template"

    name = fields.Char(string='Name', required=True)
    stage_ids = fields.One2many('stock.picking.status.stage', 'status_template_id', string='Stages', required=True)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    status_template_id = fields.Many2one('stock.picking.status.template',
                                         string='Status Template',
                                         tracking=True,
                                         domain="[('stage_ids' ,'!=', False)]",
                                         )
    status_stage = fields.Many2one('stock.picking.status.stage', string='Stage', tracking=True)
    stage_change_date = fields.Date(string='Change Date')
    expected_date = fields.Date(string='Expected Date', readonly=True)  # should fix this later on



    @api.onchange('status_stage')
    def onchange_status_stage(self):
        for rec in self:
            rec.expected_date = rec.stage_change_date + timedelta(
                days=rec.status_stage.duration) if rec.stage_change_date else False

    def _transfer_status_change(self):
        print('_transfer_status_change')
        current_date = date.today()
        print('***')
        res = self.env['mail.message'].create({'message_type': "notification",
                                               "subtype_id": self.env.ref("mail.mt_comment").id,  # subject type
                                               'body': "Need to take action on this transfer",
                                               'subject': "Action Needed YO",
                                               'partner_ids': [1, 2, 3, 4, 5, 6, 7],
                                               'model': self._name,
                                               'res_id': self.id,
                                               })
        print(res)

    def action_confirm(self):
        result = super(StockPicking, self).action_confirm()
        self.status_stage = self.status_template_id.stage_ids[0].id
        self.expected_date = self.stage_change_date + timedelta(
            days=rec.status_stage.duration) if self.stage_change_date else False
        return result
