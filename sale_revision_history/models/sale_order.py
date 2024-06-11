from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = "sale.order"

    current_revision_id = fields.Many2one('sale.order', 'Current revision', readonly=True, copy=True)
    old_revision_ids = fields.One2many('sale.order', 'current_revision_id', 'Old revisions', readonly=True,
                                       context={'active_test': False})
    revision_number = fields.Integer('Revision', copy=False)
    unrevisioned_name = fields.Char('Order Reference', copy=False, readonly=True)
    revision_reason = fields.Char('Reason Of Change', copy=False, readonly=True)
    active = fields.Boolean('Active', default=True, copy=True)

    @api.model
    def create(self, vals):
        if 'unrevisioned_name' not in vals:
            if vals.get('name', 'New') == 'New':
                seq = self.env['ir.sequence']
                vals['name'] = seq.next_by_code('sale.order') or '/'
            vals['unrevisioned_name'] = vals['name']
        return super(SaleOrder, self).create(vals)

    def action_revision(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Revision Reason'),
            'res_model': 'revision.reason',
            'view_mode': 'form',
            'target': 'new',
            'nodestroy': True,
            'context': {
                'default_sale_id': self.id
            },
        }

    def action_view_revision_wizard(self, reason):
        self.ensure_one()
        view_ref = self.env.ref('sale.view_order_form', False)
        view_id = view_ref.id
        self.with_context(sale_revision_history=True, reason=reason).copy()
        self.write({'state': 'draft'})
        self.name = '%s-%02d' % (self.name, self.revision_number + 1)
        self.order_line.write({'state': 'draft'})
        #         self.mapped('order_line').write(
        #             {'sale_line_id': False})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sales Order'),
            'res_model': 'sale.order',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': view_id,
            'target': 'current',
            'nodestroy': True,
        }

    @api.returns('self', lambda value: value.id)
    def copy(self, defaults=None):
        if not defaults:
            defaults = {}
        # if not self.unrevisioned_name:
        #     self.unrevisioned_name = self.name
        if self.env.context.get('sale_revision_history'):
            reason = self.env.context.get('reason')
            defaults.update({
                'name': self.name,
                'revision_number': self.revision_number,
                'revision_reason': reason,
                'active': True,
                'state': 'cancel',
                'current_revision_id': self.id,
                'unrevisioned_name': self.unrevisioned_name,
            })
            self.write({
                'revision_number': self.revision_number + 1,
                # 'name': '%s-%02d' % (self.unrevisioned_name, revno + 1)
            })
        return super(SaleOrder, self).copy(defaults)
