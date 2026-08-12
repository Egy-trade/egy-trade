# -*- coding: utf-8 -*-
"""Quotation-level VAT and withholding controls.

This module deliberately *uses* Finance's existing tax configuration.  It
never creates a tax, account, tag, move, or invoice: standard Odoo owns the
accounting document lifecycle.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare

from .sale_order_offer_dates import _is_offer_date_internal


_FINANCE_INTERNAL_TOKEN = object()
# Imported by the confirmation/revision service.  Context values can only pass
# this exact in-process object, so RPC/import cannot forge the privilege.
_RETENTION_REVISION_TOKEN = object()


def _is_finance_internal(env):
    return env.context.get('_finance_internal_token') is _FINANCE_INTERNAL_TOKEN


def _is_retention_revision_internal(env):
    return env.context.get('_retention_revision_token') is _RETENTION_REVISION_TOKEN


class ResCompany(models.Model):
    _inherit = 'res.company'

    quotation_vat_tax_id = fields.Many2one(
        'account.tax', string='Quotation VAT Tax',
        help='Finance-configured existing 14% sales VAT; this module does not create it.')
    quotation_retention_tax_id = fields.Many2one(
        'account.tax', string='Quotation Withholding Tax',
        help='Finance-configured existing negative 1% sales withholding tax.')
    quotation_withholding_responsible_id = fields.Many2one(
        'res.users', string='Withholding Evidence Responsible',
        help='Accounting user responsible for collecting customer withholding evidence.')
    quotation_standard_payment_term_id = fields.Many2one(
        'account.payment.term', string='Standard Quotation Payment Terms')
    quotation_standard_incoterm_id = fields.Many2one(
        'account.incoterms', string='Standard Quotation Delivery Terms')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    quotation_vat_tax_id = fields.Many2one(related='company_id.quotation_vat_tax_id', readonly=False)
    quotation_retention_tax_id = fields.Many2one(related='company_id.quotation_retention_tax_id', readonly=False)
    quotation_withholding_responsible_id = fields.Many2one(
        related='company_id.quotation_withholding_responsible_id', readonly=False)
    quotation_standard_payment_term_id = fields.Many2one(
        related='company_id.quotation_standard_payment_term_id', readonly=False)
    quotation_standard_incoterm_id = fields.Many2one(
        related='company_id.quotation_standard_incoterm_id', readonly=False)


class SaleOrderFinanceApproval(models.Model):
    _name = 'sale.order.finance.approval'
    _description = 'Quotation Approval Audit'
    _order = 'approval_date desc, id desc'

    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade', index=True)
    code = fields.Char(required=True, index=True)
    label = fields.Char(required=True)
    approver_id = fields.Many2one('res.users', required=True, readonly=True)
    approval_date = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now)
    reason = fields.Text(required=True)
    invalidated = fields.Boolean(readonly=True, default=False)
    invalidated_reason = fields.Char(readonly=True)
    invalidated_date = fields.Datetime(readonly=True)
    carried_from_approval_id = fields.Many2one('sale.order.finance.approval', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        if not _is_finance_internal(self.env):
            raise AccessError(_('Quotation approvals are created only through a controlled action.'))
        return super().create(vals_list)

    def write(self, vals):
        if not _is_finance_internal(self.env):
            raise AccessError(_('Quotation approval audit records cannot be edited directly.'))
        return super().write(vals)

    def unlink(self):
        raise AccessError(_('Quotation approval audit records cannot be deleted.'))


class SaleOrderWithholdingEvidence(models.Model):
    _name = 'sale.order.withholding.evidence'
    _description = 'Customer Withholding Evidence'
    _order = 'id desc'

    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade', readonly=True, index=True)
    partner_id = fields.Many2one(related='order_id.partner_id', store=True, readonly=True)
    invoice_id = fields.Many2one('account.move', readonly=True, copy=False)
    activity_id = fields.Many2one('mail.activity', readonly=True, copy=False)
    responsible_id = fields.Many2one('res.users', readonly=True, copy=False)
    tax_id = fields.Many2one('account.tax', readonly=True, required=True)
    currency_id = fields.Many2one(related='order_id.currency_id', readonly=True)
    expected_basis = fields.Monetary(readonly=True)
    expected_amount = fields.Monetary(readonly=True)
    evidence_attachment_ids = fields.Many2many('ir.attachment', string='Customer Evidence', copy=False)
    remittance_reference = fields.Char(copy=False)
    payment_remittance_date = fields.Date(copy=False)
    status = fields.Selection([
        ('pending', 'Pending Customer Evidence'), ('received', 'Evidence Received'),
        ('waived', 'Waived'), ('cancelled', 'Order Cancelled'),
    ], default='pending', required=True, readonly=True, copy=False)
    closure_reason = fields.Text(readonly=True, copy=False)
    closed_by = fields.Many2one('res.users', readonly=True, copy=False)
    closed_at = fields.Datetime(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        if not _is_finance_internal(self.env):
            raise AccessError(_('Withholding evidence tasks are created only when an eligible Sales Order is confirmed.'))
        return super().create(vals_list)

    def action_mark_received(self):
        if not (self.env.is_superuser() or self.env.user.has_group('account.group_account_manager')):
            raise AccessError(_('Only an Accounting Manager may close withholding evidence.'))
        if any(not evidence.evidence_attachment_ids for evidence in self):
            raise ValidationError(_('Attach the customer withholding evidence before closing this task.'))
        result = self.with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({
            'status': 'received', 'closed_by': self.env.user.id, 'closed_at': fields.Datetime.now(),
        })
        for evidence in self.filtered('activity_id'):
            evidence.activity_id.sudo().action_done(
                feedback=_('Customer withholding evidence received.')
            )
        return result

    def action_waive(self, reason):
        if not (self.env.is_superuser() or self.env.user.has_group('account.group_account_manager')):
            raise AccessError(_('Only an Accounting Manager may waive withholding evidence.'))
        if not (reason or '').strip():
            raise ValidationError(_('A reason is required to waive withholding evidence.'))
        result = self.with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({
            'status': 'waived', 'closure_reason': reason, 'closed_by': self.env.user.id,
            'closed_at': fields.Datetime.now(),
        })
        for evidence in self.filtered('activity_id'):
            evidence.activity_id.sudo().action_done(
                feedback=_('Withholding evidence follow-up waived: %s') % reason
            )
        return result

    def write(self, vals):
        protected = {'order_id', 'partner_id', 'invoice_id', 'activity_id', 'responsible_id', 'tax_id', 'expected_basis',
                     'expected_amount', 'status', 'closure_reason', 'closed_by', 'closed_at'}
        if protected.intersection(vals) and not _is_finance_internal(self.env):
            raise AccessError(_('Withholding evidence lifecycle fields are system-managed.'))
        evidence_fields = {
            'evidence_attachment_ids', 'remittance_reference',
            'payment_remittance_date',
        }
        if (evidence_fields.intersection(vals) and not _is_finance_internal(self.env)
                and self.filtered(lambda evidence: evidence.status != 'pending')):
            raise AccessError(_(
                'Received, waived, or cancelled withholding evidence is immutable. '
                'Record a new audited follow-up instead of rewriting closed evidence.'
            ))
        return super().write(vals)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    apply_vat = fields.Boolean(string='14% VAT', default=True, copy=True)
    apply_withholding = fields.Boolean(string='1% Withholding', default=False, copy=True)
    vat_exemption_reason = fields.Text(string='VAT Exemption Reason', copy=True)
    vat_exemption_requested_by = fields.Many2one('res.users', readonly=True, copy=False)
    vat_exemption_requested_at = fields.Datetime(readonly=True, copy=False)
    tax_selection_review_required = fields.Boolean(readonly=True, copy=False)
    finance_approval_ids = fields.One2many('sale.order.finance.approval', 'order_id', readonly=True, copy=False)
    finance_approval_reason = fields.Text(help='Reason recorded for a manager approval.')
    finance_approval_required = fields.Boolean(compute='_compute_finance_approval_required', compute_sudo=True)
    withholding_evidence_ids = fields.One2many('sale.order.withholding.evidence', 'order_id', readonly=True, copy=False)

    def _quotation_manager(self):
        user = self.env.user
        return self.env.is_superuser() or user.has_group('sale_order_product_pricing.quotation_manager_group') or user.has_group('sales_team.group_sale_manager')

    def _finance_manager(self):
        return self._quotation_manager() or self.env.user.has_group('account.group_account_manager')

    def _can_select_quotation_taxes(self):
        return (
            self.env.is_superuser()
            or self.env.user.has_group('sales_team.group_sale_salesman')
            or self.env.user.has_group(
                'sale_order_product_pricing.quotation_specialist_group'
            )
        )

    def _validate_quotation_tax(self, tax, amount, label):
        self.ensure_one()
        if not tax:
            raise UserError(_('Finance must configure the existing %(label)s tax before it can be selected.') % {'label': label})
        if tax.company_id != self.company_id or tax.type_tax_use != 'sale' or tax.amount_type != 'percent' or float_compare(tax.amount, amount, precision_digits=4):
            raise ValidationError(_('The configured %(label)s tax is not a valid %(amount)s%% sales tax for this company.') % {'label': label, 'amount': abs(amount)})
        return tax

    def _quotation_effective_tax(self, tax):
        """Return the existing tax after Odoo's normal fiscal-position mapping."""
        self.ensure_one()
        if not tax:
            return self.env['account.tax']
        if self.fiscal_position_id:
            return self.fiscal_position_id.map_tax(
                tax, product=False, partner=self.partner_shipping_id,
            )
        return tax

    def _quotation_selected_tax_ids(self):
        self.ensure_one()
        taxes = self.env['account.tax']
        if self.apply_vat:
            taxes |= self._validate_quotation_tax(self.company_id.quotation_vat_tax_id, 14.0, _('14% VAT'))
        if self.apply_withholding:
            taxes |= self._validate_quotation_tax(self.company_id.quotation_retention_tax_id, -1.0, _('negative 1% withholding'))
        # Keep the header convenient without bypassing Odoo's normal fiscal
        # position mapping.  The configured company taxes are policy inputs;
        # the mapped sales taxes are what belong on this customer's lines.
        return self._quotation_effective_tax(taxes)

    def get_quotation_tax_selection(self):
        self.ensure_one()
        return {'apply_vat': self.apply_vat, 'apply_withholding': self.apply_withholding,
                'vat_exemption_reason': self.vat_exemption_reason or False}

    def _apply_quotation_tax_selection(self):
        for order in self:
            taxes = order._quotation_selected_tax_ids()
            order.order_line.filtered(lambda line: not line.display_type).with_context(
                _finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({'tax_id': [(6, 0, taxes.ids)]})
        return True

    def set_quotation_tax_selection(self, apply_vat, apply_withholding, vat_exemption_reason=False):
        """Public UI/RPC entry point; the write guard provides the same protection."""
        return self.write({'apply_vat': bool(apply_vat), 'apply_withholding': bool(apply_withholding),
                           'vat_exemption_reason': vat_exemption_reason or False})

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for incoming in vals_list:
            vals = dict(incoming)
            vals.pop('tax_treatment', None)  # retire CIF/combined policy from imports too
            if ({'apply_vat', 'apply_withholding', 'vat_exemption_reason'} & set(vals)
                    and not self._can_select_quotation_taxes()):
                raise AccessError(_(
                    'Only Sales and Quotation Specialists may select quotation taxes.'
                ))
            vals.setdefault('apply_vat', True)
            vals.setdefault('apply_withholding', False)
            company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
            days = vals.get('offer_expiry_days', company.quotation_expiry_days_default)
            if days != company.quotation_expiry_days_default:
                if not self._finance_manager():
                    raise AccessError(_('Only Quotation, Sales, or Accounting Managers may override Days of Expiry.'))
                if not (vals.get('finance_approval_reason') or '').strip():
                    raise ValidationError(_('A stated reason is required for a Days of Expiry override.'))
            if not vals['apply_vat'] and not (vals.get('vat_exemption_reason') or '').strip():
                raise ValidationError(_('A VAT exemption reason is required when 14% VAT is not selected.'))
            if not vals['apply_vat']:
                vals['vat_exemption_requested_by'] = self.env.user.id
                vals['vat_exemption_requested_at'] = fields.Datetime.now()
            prepared.append(vals)
        orders = super().create(prepared)
        # Do not invent a fallback tax when the company has not yet completed setup.
        for order in orders:
            if (order.apply_vat and order.company_id.quotation_vat_tax_id) or (order.apply_withholding and order.company_id.quotation_retention_tax_id):
                order._apply_quotation_tax_selection()
            if order.offer_expiry_days != order.company_id.quotation_expiry_days_default:
                order.message_post(body=_('Days of Expiry overridden to %(days)s by %(user)s: %(reason)s') % {
                    'days': order.offer_expiry_days, 'user': self.env.user.display_name,
                    'reason': order.finance_approval_reason,
                })
        return orders

    @api.onchange('offer_expiry_days')
    def _onchange_finance_offer_expiry_days(self):
        for order in self:
            if order.offer_expiry_days != order.company_id.quotation_expiry_days_default:
                return {'warning': {
                    'title': _('Validity override'),
                    'message': _('Only a Quotation, Sales, or Accounting Manager may override Days of Expiry. State the reason before saving.'),
                }}

    def _finance_requirement_codes(self):
        self.ensure_one()
        order = self.sudo()
        requirements = {}
        lines = order.order_line.filtered(lambda line: not line.display_type)
        if any(line.price_origin == 'edited' and not line._is_authorized_foc() for line in lines):
            requirements['manual_price'] = _('Manual selling price')
        assigned_caps = [(getattr(user, 'standard_discount_cap', getattr(user, 'max_discount', 0.0)) or 0.0)
                         for user in (order.user_id | order.quotation_specialist_id)]
        company_cap = getattr(order.company_id, 'standard_discount_maximum', 30.0) or 0.0
        if any(line.standard_discount_override_used or line.discount > min(max(assigned_caps or [0.0]), company_cap, 30.0) for line in lines):
            requirements['discount_override'] = _('Discount override')
        if order.company_id.quotation_standard_payment_term_id and order.payment_term_id != order.company_id.quotation_standard_payment_term_id:
            requirements['nonstandard_payment_terms'] = _('Nonstandard payment terms')
        if order.company_id.quotation_standard_incoterm_id and order.incoterm != order.company_id.quotation_standard_incoterm_id:
            requirements['nonstandard_delivery_terms'] = _('Nonstandard delivery terms')
        if order.offer_expiry_days != order.company_id.quotation_expiry_days_default:
            requirements['validity_override'] = _('Validity override')
        eur = self.env.ref('base.EUR')
        order_date = fields.Date.to_date(order.date_order) or fields.Date.context_today(order)
        if order.currency_id._convert(order.amount_untaxed, eur, order.company_id, order_date) >= 100000.0:
            requirements['high_value'] = _('Untaxed EUR-equivalent value of EUR 100,000 or more')
        if not order.apply_vat:
            requirements['vat_exemption'] = _('VAT exemption')
        return requirements

    @api.depends('apply_vat', 'vat_exemption_reason', 'order_line.price_origin', 'order_line.discount',
                 'order_line.standard_discount_override_used', 'payment_term_id', 'incoterm',
                 'offer_expiry_days', 'amount_untaxed', 'currency_id', 'finance_approval_ids.invalidated')
    def _compute_finance_approval_required(self):
        for order in self:
            order.finance_approval_required = bool(order._finance_requirement_codes())

    def _invalidate_finance_approvals(self, reason):
        approvals = self.sudo().mapped('finance_approval_ids').filtered(lambda approval: not approval.invalidated)
        if approvals:
            approvals.with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({
                'invalidated': True, 'invalidated_reason': reason, 'invalidated_date': fields.Datetime.now(),
            })
            for order in self:
                order.message_post(body=_('Quotation approvals invalidated: %s') % reason)

    def action_approve_finance_requirements(self):
        if not self._quotation_manager():
            raise AccessError(_('Only Quotation Managers and Sales Managers may approve quotation exceptions.'))
        for order in self:
            order.check_access_rights('write')
            order.check_access_rule('write')
            # ``active`` and ``current_revision_id`` are supplied by the
            # optional lifecycle module, which is installed after this module
            # on a clean database.  Keep the approval gate valid both with and
            # without that extension loaded.
            if (order.state != 'draft' or not getattr(order, 'active', True)
                    or getattr(order, 'current_revision_id', False)):
                raise UserError(_(
                    'Commercial exceptions may be approved only on the active current draft.'
                ))
            requirements = order._finance_requirement_codes()
            current = order.sudo().finance_approval_ids.filtered(lambda approval: not approval.invalidated)
            approved = set(current.mapped('code'))
            for code, label in requirements.items():
                if code not in approved:
                    reason = order.vat_exemption_reason if code == 'vat_exemption' else order.finance_approval_reason
                    if not (reason or '').strip():
                        raise ValidationError(_('A reason is required before approving %(label)s.') % {'label': label})
                    self.env['sale.order.finance.approval'].sudo().with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).create({
                        'order_id': order.id, 'code': code, 'label': label, 'approver_id': self.env.user.id, 'reason': reason,
                    })
        return True

    def _check_finance_issue_requirements(self):
        for order in self:
            if order.tax_selection_review_required:
                raise UserError(_(
                    'Issue Offer PDF is blocked: this migrated draft has a mixed or '
                    'ambiguous legacy tax selection. Review and save the quotation '
                    'Taxes selection first.'
                ))
            lines = order.order_line.filtered(lambda line: not line.display_type)
            if lines.filtered(lambda line: getattr(line, 'is_add_below_placeholder', False) or not line.product_id or not line.product_uom):
                raise UserError(_('Issue Offer PDF is blocked: complete or remove every blank Add Below product row.'))
            expected = order._quotation_selected_tax_ids()
            if any(line.tax_id != expected for line in lines):
                raise UserError(_('Issue Offer PDF is blocked: commercial line taxes must match the quotation Taxes selection.'))
            if not order.apply_vat and not (order.vat_exemption_reason or '').strip():
                raise UserError(_('Issue Offer PDF is blocked: enter the VAT exemption reason.'))
            if order.apply_withholding and not order.company_id.quotation_withholding_responsible_id:
                raise UserError(_(
                    'Issue Offer PDF is blocked: configure the Accounting user responsible '
                    'for collecting customer withholding evidence.'
                ))
            if lines.filtered(lambda line: float_compare(line.price_unit, 0.0, precision_rounding=order.currency_id.rounding) == 0 and not line._is_authorized_foc()):
                raise UserError(_('Issue Offer PDF is blocked: every zero-price line must be authorized Free of Charge.'))
            requirements = order._finance_requirement_codes()
            approved = set(order.sudo().finance_approval_ids.filtered(lambda approval: not approval.invalidated).mapped('code'))
            missing = [label for code, label in requirements.items() if code not in approved]
            if missing:
                raise UserError(_('Issue Offer PDF requires approval for: %s.') % ', '.join(missing))
        return True

    def _retention_only_fingerprint(self):
        self.ensure_one()
        line_signature = tuple((line.display_type, line.product_id.id, line.name, line.product_uom_qty,
                                line.product_uom.id, line.price_unit, line.discount,
                                getattr(line, 'discount_2', 0.0), getattr(line, 'discount_3', 0.0),
                                tuple(sorted((line.tax_id - self.company_id.quotation_retention_tax_id).ids)))
                               for line in self.order_line)
        incoterm = getattr(self, 'incoterm_id', False) or getattr(self, 'incoterm', False)
        return (self.partner_id.id, self.partner_invoice_id.id, self.partner_shipping_id.id, self.currency_id.id,
                self.pricelist_id.id, self.payment_term_id.id, self.fiscal_position_id.id,
                incoterm.id if incoterm else False, self.client_order_ref, self.note,
                getattr(self, 'ks_enable_discount', False), getattr(self, 'ks_global_discount_type', False),
                getattr(self, 'ks_global_discount_rate', 0.0), self.apply_vat, self.vat_exemption_reason or '', line_signature)

    def _carry_retention_only_approvals_from(self, source_order):
        """Narrow internal hook used after lifecycle's issued-offer comparison."""
        if not _is_retention_revision_internal(self.env):
            raise AccessError(_('Approval carry-forward is only available from the controlled confirmation workflow.'))
        self.ensure_one()
        source_order.ensure_one()
        canonical_source = getattr(source_order, '_commercial_fingerprint', lambda: False)()
        canonical_target = getattr(self, '_commercial_fingerprint', lambda: False)()
        same_commercial_offer = (
            canonical_source == canonical_target if canonical_source and canonical_target
            else source_order._retention_only_fingerprint() == self._retention_only_fingerprint()
        )
        if source_order.state != 'sent' or self.state != 'draft' or not same_commercial_offer:
            raise ValidationError(_('Approval carry-forward is allowed only for a retention-only revision of the same commercial offer.'))
        source_approvals = source_order.sudo().finance_approval_ids.filtered(lambda approval: not approval.invalidated)
        for approval in source_approvals:
            self.env['sale.order.finance.approval'].sudo().with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).create({
                'order_id': self.id, 'code': approval.code, 'label': approval.label, 'approver_id': approval.approver_id.id,
                'approval_date': approval.approval_date, 'reason': approval.reason, 'carried_from_approval_id': approval.id,
            })
        return True

    def action_apply_retention_only_revision(self, source_order, expected_fingerprint, apply_withholding):
        """Change only withholding on a freshly copied successor.

        This is intentionally not a generic revision API.  The caller must be
        the in-process confirmation service and this method independently
        verifies the issued source, family link and its commercial fingerprint.
        """
        if not _is_retention_revision_internal(self.env):
            raise AccessError(_('A retention-only revision can only be made by the controlled confirmation workflow.'))
        self.ensure_one()
        source_order = source_order.exists()
        if (not source_order or source_order.state != 'sent'
                or not getattr(self, 'active', True) or self.state != 'draft'):
            raise ValidationError(_('A retention-only revision requires an issued offer and its active draft successor.'))
        if getattr(source_order, 'current_revision_id', self) != self:
            raise ValidationError(_('The draft is not the current successor of the issued offer.'))
        fingerprint = getattr(source_order, '_commercial_fingerprint', lambda: False)()
        target_fingerprint = getattr(self, '_commercial_fingerprint', lambda: False)()
        if not fingerprint or fingerprint != expected_fingerprint or target_fingerprint != expected_fingerprint:
            raise ValidationError(_('The revision is not identical to the issued offer apart from withholding.'))
        if not isinstance(apply_withholding, bool) or apply_withholding == source_order.apply_withholding:
            raise ValidationError(_('A retention-only revision must explicitly select the opposite withholding decision.'))
        # The copy starts with the source selection.  Toggle only the selected
        # existing withholding tax, then recreate audit approvals from source.
        self.with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({
            'apply_withholding': apply_withholding,
        })
        self._apply_quotation_tax_selection()
        self._carry_retention_only_approvals_from(source_order)
        return True

    def _create_pending_withholding_evidence(self):
        for order in self:
            if not order.apply_withholding or order.withholding_evidence_ids.filtered(lambda task: task.status == 'pending'):
                continue
            tax = order._validate_quotation_tax(order.company_id.quotation_retention_tax_id, -1.0, _('negative 1% withholding'))
            amount = order.currency_id.round(abs(order.amount_untaxed * tax.amount / 100.0))
            responsible = order.company_id.quotation_withholding_responsible_id
            evidence = self.env['sale.order.withholding.evidence'].sudo().with_context(
                _finance_internal_token=_FINANCE_INTERNAL_TOKEN).create({
                'order_id': order.id, 'responsible_id': responsible.id,
                'tax_id': tax.id, 'expected_basis': order.currency_id.round(order.amount_untaxed), 'expected_amount': amount,
            })
            if responsible:
                activity = self.env['mail.activity'].sudo().create({
                    'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                    'res_model_id': self.env['ir.model']._get_id('sale.order'),
                    'res_id': order.id,
                    'user_id': responsible.id,
                    'summary': _('Collect customer 1% withholding evidence'),
                    'note': _(
                        'Collect the customer withholding certificate and remittance '
                        'reference, then close the Withholding Evidence record.'
                    ),
                })
                evidence.with_context(
                    _finance_internal_token=_FINANCE_INTERNAL_TOKEN,
                ).write({'activity_id': activity.id})
        return True

    def action_cancel(self):
        result = super().action_cancel()
        pending = self.sudo().mapped('withholding_evidence_ids').filtered(lambda item: item.status == 'pending')
        if pending:
            activities = pending.mapped('activity_id')
            pending.with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({
                'status': 'cancelled', 'closure_reason': _('Sales Order cancelled.'),
                'closed_by': self.env.user.id, 'closed_at': fields.Datetime.now(),
            })
            for activity in activities:
                activity.sudo().action_done(
                    feedback=_('Sales Order cancelled; withholding follow-up closed.')
                )
        return result

    def write(self, vals):
        if _is_finance_internal(self.env) or _is_offer_date_internal(self.env):
            return super().write(vals)
        vals = dict(vals)
        vals.pop('tax_treatment', None)
        protected = {'vat_exemption_requested_by', 'vat_exemption_requested_at', 'tax_selection_review_required'}
        if protected.intersection(vals):
            raise AccessError(_('VAT exception and migration audit fields are system-managed.'))
        selection_fields = {'apply_vat', 'apply_withholding', 'vat_exemption_reason'}
        changing_selection = selection_fields.intersection(vals)
        if changing_selection and not (
                self._can_select_quotation_taxes()
                or _is_retention_revision_internal(self.env)):
            raise AccessError(_(
                'Only Sales and Quotation Specialists may select quotation taxes.'
            ))
        if changing_selection and self.filtered(lambda order: order.state != 'draft') and not _is_retention_revision_internal(self.env):
            raise UserError(_('Taxes are locked after an offer is issued. Create a revision.'))
        expiry_changes = self.filtered(lambda order: 'offer_expiry_days' in vals and vals['offer_expiry_days'] != order.offer_expiry_days)
        if expiry_changes:
            if not self._finance_manager():
                raise AccessError(_('Only Quotation, Sales, or Accounting Managers may override Days of Expiry.'))
            for order in expiry_changes.filtered(lambda item: vals['offer_expiry_days'] != item.company_id.quotation_expiry_days_default):
                if not (vals.get('finance_approval_reason', order.finance_approval_reason) or '').strip():
                    raise ValidationError(_('A stated reason is required for a Days of Expiry override.'))
        if any(not vals.get('apply_vat', order.apply_vat) for order in self):
            for order in self:
                final_vat = vals.get('apply_vat', order.apply_vat)
                reason = vals.get('vat_exemption_reason', order.vat_exemption_reason)
                if not final_vat and not (reason or '').strip():
                    raise ValidationError(_('A VAT exemption reason is required when 14% VAT is not selected.'))
            if not vals.get('apply_vat', all(self.mapped('apply_vat'))):
                vals['vat_exemption_requested_by'] = self.env.user.id
                vals['vat_exemption_requested_at'] = fields.Datetime.now()
        commercial_fields = {
            'partner_id', 'partner_invoice_id', 'partner_shipping_id',
            'pricelist_id', 'currency_id', 'payment_term_id',
            'fiscal_position_id', 'incoterm', 'incoterm_id',
            'client_order_ref', 'note', 'user_id', 'quotation_specialist_id',
            'sale_order_template_id', 'sale_order_option_ids', 'warehouse_id',
            'commitment_date', 'offer_expiry_days', 'validity_date',
            'offer_date', 'product_pricing', 'global_factor',
            'currency_estimate_id', 'currency_rate_estimate',
            'currency_rate_inverse', 'change_currency_rate_type',
            'change_currency_rate', 'discount_type', 'discount_rate',
            'ks_enable_discount', 'ks_global_discount_type',
            'ks_global_discount_rate',
        }
        becomes_confirmed = vals.get('state') == 'sale'
        result = super().write(vals)
        if changing_selection:
            self._apply_quotation_tax_selection()
            if self.filtered('tax_selection_review_required'):
                self.with_context(
                    _finance_internal_token=_FINANCE_INTERNAL_TOKEN,
                ).write({'tax_selection_review_required': False})
        if {'apply_vat', 'vat_exemption_reason'}.intersection(vals):
            self._invalidate_finance_approvals(_('VAT selection or VAT exemption changed.'))
        elif commercial_fields.intersection(vals):
            self._invalidate_finance_approvals(_('Commercial header changed.'))
        for order in expiry_changes.filtered(lambda item: vals['offer_expiry_days'] != item.company_id.quotation_expiry_days_default):
            order.message_post(body=_('Days of Expiry overridden to %(days)s by %(user)s: %(reason)s') % {
                'days': vals['offer_expiry_days'], 'user': self.env.user.display_name,
                'reason': vals.get('finance_approval_reason', order.finance_approval_reason),
            })
        if becomes_confirmed:
            self.filtered(lambda order: order.state == 'sale')._create_pending_withholding_evidence()
        return result

    def _create_invoices(self, *args, **kwargs):
        """Let standard Odoo create drafts, then link the first evidence task.

        No invoice is created by confirmation and no accounting value is
        calculated here; the link only helps Accounting collect the later
        customer certificate against the document Odoo actually created.
        """
        invoices = super()._create_invoices(*args, **kwargs)
        for order in self:
            evidence = order.withholding_evidence_ids.filtered(
                lambda item: item.status == 'pending' and not item.invoice_id
            )[:1]
            related = invoices.filtered(
                lambda move: order in move.invoice_line_ids.sale_line_ids.order_id
            )[:1]
            if evidence and related:
                evidence.with_context(
                    _finance_internal_token=_FINANCE_INTERNAL_TOKEN,
                ).write({'invoice_id': related.id})
        return invoices


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_free_of_charge = fields.Boolean(string='Free of Charge', copy=True)
    free_of_charge_reason = fields.Text(string='Free of Charge Reason', copy=True)
    free_of_charge_authorized_by = fields.Many2one('res.users', readonly=True, copy=False)
    free_of_charge_authorized_at = fields.Datetime(readonly=True, copy=False)

    def _is_authorized_foc(self):
        self.ensure_one()
        return bool(float_compare(self.price_unit, 0.0, precision_rounding=self.order_id.currency_id.rounding) == 0
                    and self.is_free_of_charge and (self.free_of_charge_reason or '').strip()
                    and self.free_of_charge_authorized_by and self.free_of_charge_authorized_at)

    def _can_authorize_foc(self):
        return self.env.is_superuser() or self.env.user.has_group('sale_order_product_pricing.product_pricing_group') or self.env.user.has_group('sale_order_product_pricing.quotation_manager_group') or self.env.user.has_group('sales_team.group_sale_manager')

    @staticmethod
    def _uses_quotation_tax_policy(order):
        return bool(order and (order.company_id.quotation_vat_tax_id or order.company_id.quotation_retention_tax_id))

    @api.model_create_multi
    def create(self, vals_list):
        if not _is_finance_internal(self.env):
            vals_list = [dict(vals) for vals in vals_list]
            for vals in vals_list:
                if {'free_of_charge_authorized_by', 'free_of_charge_authorized_at'}.intersection(vals):
                    raise AccessError(_('Free of Charge authorization evidence is system-managed.'))
                if vals.get('is_free_of_charge'):
                    if not self._can_authorize_foc():
                        raise AccessError(_('Only an authorized Pricing User, Quotation Manager, or Sales Manager may mark a line Free of Charge.'))
                    if not (vals.get('free_of_charge_reason') or '').strip():
                        raise ValidationError(_('A Free of Charge reason is required.'))
                    vals.update({'free_of_charge_authorized_by': self.env.user.id, 'free_of_charge_authorized_at': fields.Datetime.now()})
                order = self.env['sale.order'].browse(vals.get('order_id')).exists()
                if 'tax_id' in vals and self._uses_quotation_tax_policy(order):
                    vals.pop('tax_id')
        lines = super().create(vals_list)
        if not _is_finance_internal(self.env):
            for order in lines.mapped('order_id'):
                if self._uses_quotation_tax_policy(order):
                    lines.filtered(lambda line: line.order_id == order and not line.display_type).with_context(
                        _finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({'tax_id': [(6, 0, order._quotation_selected_tax_ids().ids)]})
        if not _is_finance_internal(self.env):
            lines.mapped('order_id')._invalidate_finance_approvals(_('Commercial line added.'))
        return lines

    def write(self, vals):
        if not _is_finance_internal(self.env) and 'tax_id' in vals and any(self._uses_quotation_tax_policy(order) for order in self.mapped('order_id')):
            raise UserError(_('Direct line-tax edits are restricted. Change Taxes on the quotation header.'))
        vals = dict(vals)
        if not _is_finance_internal(self.env):
            if {'free_of_charge_authorized_by', 'free_of_charge_authorized_at'}.intersection(vals):
                raise AccessError(_('Free of Charge authorization evidence is system-managed.'))
            if {'is_free_of_charge', 'free_of_charge_reason'}.intersection(vals):
                if not self._can_authorize_foc():
                    raise AccessError(_('Only an authorized Pricing User, Quotation Manager, or Sales Manager may change Free of Charge details.'))
                for line in self:
                    if vals.get('is_free_of_charge', line.is_free_of_charge) and not (vals.get('free_of_charge_reason', line.free_of_charge_reason) or '').strip():
                        raise ValidationError(_('A Free of Charge reason is required.'))
                if vals.get('is_free_of_charge'):
                    vals.update({'free_of_charge_authorized_by': self.env.user.id, 'free_of_charge_authorized_at': fields.Datetime.now()})
        result = super().write(vals)
        if not _is_finance_internal(self.env) and {
                'sequence', 'product_id', 'name', 'product_uom_qty',
                'product_uom', 'price_unit', 'discount', 'discount_2',
                'discount_3', 'purchase_price_estimate', 'factor',
                'line_factor', 'is_free_of_charge', 'free_of_charge_reason',
        }.intersection(vals):
            self.mapped('order_id')._invalidate_finance_approvals(_('Commercial line changed.'))
        return result

    def unlink(self):
        orders = self.mapped('order_id')
        result = super().unlink()
        if not _is_finance_internal(self.env):
            orders._invalidate_finance_approvals(_('Commercial line removed.'))
        return result


class SaleOrderOption(models.Model):
    _inherit = 'sale.order.option'

    @api.model_create_multi
    def create(self, vals_list):
        options = super().create(vals_list)
        options.mapped('order_id')._invalidate_finance_approvals(
            _('Optional product added.')
        )
        return options

    def write(self, vals):
        result = super().write(vals)
        if {'sequence', 'product_id', 'name', 'quantity', 'uom_id', 'price_unit', 'discount'}.intersection(vals):
            self.mapped('order_id')._invalidate_finance_approvals(
                _('Optional product changed.')
            )
        return result

    def unlink(self):
        orders = self.mapped('order_id')
        result = super().unlink()
        orders._invalidate_finance_approvals(_('Optional product removed.'))
        return result
