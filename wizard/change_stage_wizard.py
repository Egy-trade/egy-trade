# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ChangeStageWizard(models.TransientModel):
    _name = 'change.stage.wizard'

    stage = fields.Many2one('stock.picking.status.stage')
    change_date = fields.Date(string='Date', default=fields.date.today())
    status_template_id = fields.Many2one('stock.picking.status.template')

    @api.model
    def default_get(self, fields):
        stock_picking_id = self._context['stock_picking_id'] # not sure about this one
        status_template_id = self._context['status_template_id']
        result = super(ChangeStageWizard, self).default_get(fields)
        result['status_template_id'] = status_template_id
        return result

    def change_stage(self):
        pass
