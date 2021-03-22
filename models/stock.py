# -*- coding: utf-8 -*-

from odoo import models, fields


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
    stage_ids = fields.One2many('stock.picking.status.stage', 'status_template_id', string='Stages')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    status_template_id = fields.Many2one('stock.picking.status.template', string='Status Template')
    shipment_state = fields.Selection([
        ('waiting', 'Waiting'),
        ('shipped', 'Shipped'),
        ('customs', 'Customs'),
    ], string='Shipment Status', tracking=True, default='waiting', required=True)
