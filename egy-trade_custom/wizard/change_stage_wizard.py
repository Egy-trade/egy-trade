# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date, timedelta


class ChangeStageWizard(models.TransientModel):
    _name = 'change.stage.wizard'

    stage = fields.Many2one('stock.picking.status.stage')
    change_date = fields.Date(string='Transfer Date', default=fields.date.today())
    expected_date = fields.Date(string='Expected Date', readonly=True)
    status_template_id = fields.Many2one('stock.picking.status.template')
    stock_picking_id = fields.Many2one('stock.picking')

    @api.onchange('stage')
    def _onchange_stage(self):
        for rec in self:
            rec.expected_date = rec.change_date + timedelta(days=rec.stage.duration)

    @api.model
    def default_get(self, fields):
        stock_picking_id = self._context['stock_picking_id']
        status_template_id = self._context['status_template_id']
        stage_id = self._context['status_stage']
        result = super(ChangeStageWizard, self).default_get(fields)

        result['stage'] = stage_id
        result['status_template_id'] = status_template_id
        result['stock_picking_id'] = stock_picking_id
        return result

    def change_stage(self):
        self.stock_picking_id.status_stage = self.stage
        self.stock_picking_id.stage_change_date = self.change_date

        return True
