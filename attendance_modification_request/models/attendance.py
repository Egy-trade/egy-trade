from odoo import fields, models, api


class AttendanceModification(models.Model):
    _name = "attendance.modification"
    _description = "Attendance Modification Request"
    _rec_name = "ref"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    ref = fields.Char(string="Reference", readonly=True, required=True, copy=False, default='New')
    date = fields.Date(string="Date", default=fields.Date.context_today, tracking=True)
    employee_id = fields.Many2one("hr.employee", 'Employee')
    type = fields.Selection([
        ('checkin', 'Check in'),
        ('checkout', 'Check out'),
        ('both', 'Both')],
        string="Type", default='new', required=True)
    reason = fields.Text("Reason")
    action_to_do = fields.Selection([
        ('new', 'New record'),
        ('modify', 'Modification')],
        string="Type", default='new', required=True)
    attendance = fields.Many2one('hr.attendance', "Attendance", domain="[('employee_id','=',employee_id)]")
    updated_value_in = fields.Datetime(related="attendance.check_in", string="Updated Value check in", store=True,
                                       readonly=False)
    updated_value_out = fields.Datetime(related="attendance.check_out", string="Updated Value check out", store=True,
                                        readonly=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting for approval'),
        ('approved', 'Approved')],
        string="Status", default="draft")

    @api.model
    def create(self, vals):
        vals['ref'] = self.env['ir.sequence'].next_by_code('attendance.modification')
        return super(AttendanceModification, self).create(vals)

    def write(self, vals):
        if not self.ref and not vals.get('ref'):
            vals['ref'] = self.env['ir.sequence'].next_by_code('attendance.modification')
        return super(AttendanceModification, self).write(vals)

    def button_confirm(self):
        self.state = "waiting"
        if self.employee_id and self.employee_id.parent_id:
            partner_ids = [self.employee_id.parent_id.id]
            subtype_id = self.env['ir.model.data'].xmlid_to_res_id(
                'mail.mt_comment')
            self.message_post(
                body='There is a Request Has been sent.',
                partner_ids=partner_ids,
                subject='Notification Subject',
                subtype_id=subtype_id
            )

    def action_reject(self):
        action = self.env.ref('attendance_modification_request.action_cancellation_reason').read()[0]
        return action

    def action_confirm(self):
        self.state = 'approved'
