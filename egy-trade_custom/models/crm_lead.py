from odoo import models, fields


class CRMProject(models.Model):
    _name = 'crm.project'

    name = fields.Char(string='Name')


class CRMLead(models.Model):
    _inherit = 'crm.lead'

    crm_project_id = fields.Many2one('crm.project', string='Project')

    owner = fields.Many2one('res.partner', string='Owner')
    mep_contractor = fields.Many2one('res.partner', string='MEP Contractor')
    arch_consultant = fields.Many2one('res.partner', string='Architecture Consultant')
    electrical_consultant = fields.Many2one('res.partner', string='Electrical Consultant')
