# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ChangeStageWizard(models.TransientModel):
    _name = 'set.stage.wizard'

    route = fields.Many2one('stock.picking.status.template', string='Route Template')

    def set_stage(self):
        stock_picking_id = self.env.context.get('active_id')
        stock_picking = self.env['stock.picking'].browse(stock_picking_id)
        stage = self.route.stage_ids[0] if len(self.route.stage_ids) else False
        stock_picking.write({
            'status_template_id': self.route.id,
            'status_stage': stage
        })
