from email.policy import default

from odoo import models, fields, api


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

    def _compute_current_user(self):
        is_team_leader = self.env.user.has_group('egy-trade_custom.salas_team_leader')
        current_user = self.env.user
        is_sale_manger = self.env.user.has_group('sales_team.group_sale_manager')
        for rec in self:
            if rec.user_id == current_user or is_sale_manger or (
                    is_team_leader and rec.team_id.user_id == current_user):
                rec.current_user = True
            else:
                rec.current_user = False

    current_user = fields.Boolean('res.users', compute='_compute_current_user', default=True)

    @api.depends('partner_id')
    def _get_partner_allows(self):
        user = self.env.user
        all_teams = self.env['crm.team'].search([('user_id', '=', user.id)])
        team_list = [team.id for team in all_teams]
        is_team_leader = self.env.user.has_group('egy-trade_custom.salas_team_leader')
        if user.has_group('sales_team.group_sale_manager'):
            partners = self.env['res.partner'].search([('active', '=', True)])
        elif team_list and is_team_leader:
            partners = self.env['res.partner'].search([('team_id', 'in', team_list)])
            print("Partner Teams Leader ", partners)
        else:
            partners = self.env['res.partner'].search([('user_id', '=', user.id)])
            print("Partners", partners)
        self.partner_allow_ids = partners

    partner_allow_ids = fields.Many2many('res.partner', compute='_get_partner_allows')


