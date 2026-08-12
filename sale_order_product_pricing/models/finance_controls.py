# -*- coding: utf-8 -*-
"""Finance-controlled quotation gates and tax treatment.

This module deliberately stores policy references (taxes, payment terms and
incoterms) on the company.  It never manufactures accounting accounts or tax
tags: Finance owns those through the configured tax records.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare

from .sale_order_offer_dates import _is_offer_date_internal


_FINANCE_INTERNAL_TOKEN = object()


def _is_finance_internal(env):
    return env.context.get('_finance_internal_token') is _FINANCE_INTERNAL_TOKEN


class ResCompany(models.Model):
    _inherit = 'res.company'

    quotation_vat_tax_id = fields.Many2one(
        'account.tax', string='Quotation VAT Tax',
        help='Finance-configured 14% sales VAT used by Standard VAT + Retention quotations.')
    quotation_retention_tax_id = fields.Many2one(
        'account.tax', string='Quotation Retention Tax',
        help='Finance-configured negative 1% withholding tax. Its account and reporting tags are used as configured.')
    quotation_standard_payment_term_id = fields.Many2one(
        'account.payment.term', string='Standard Quotation Payment Terms')
    quotation_standard_incoterm_id = fields.Many2one(
        'account.incoterms', string='Standard Quotation Delivery Terms')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    quotation_vat_tax_id = fields.Many2one(related='company_id.quotation_vat_tax_id', readonly=False)
    quotation_retention_tax_id = fields.Many2one(related='company_id.quotation_retention_tax_id', readonly=False)
    quotation_standard_payment_term_id = fields.Many2one(
        related='company_id.quotation_standard_payment_term_id', readonly=False)
    quotation_standard_incoterm_id = fields.Many2one(
        related='company_id.quotation_standard_incoterm_id', readonly=False)


class SaleOrderFinanceApproval(models.Model):
    _name = 'sale.order.finance.approval'
    _description = 'Quotation Finance Approval'
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

    @api.model_create_multi
    def create(self, vals_list):
        if not _is_finance_internal(self.env):
            raise AccessError(_('Finance approvals are created only through the controlled approval action.'))
        return super().create(vals_list)

    def write(self, vals):
        if not _is_finance_internal(self.env):
            raise AccessError(_('Finance approval audit records cannot be edited directly.'))
        return super().write(vals)

    def unlink(self):
        raise AccessError(_('Finance approval audit records cannot be deleted.'))


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    tax_treatment = fields.Selection([
        ('standard', 'Standard VAT 14% + Retention 1%'),
        ('cif_no_taxes', 'CIF - No Taxes'),
    ], default='standard', required=True, copy=True,
       help='Finance policy for line taxes. Use the header; direct line-tax edits are restricted.')
    finance_approval_ids = fields.One2many('sale.order.finance.approval', 'order_id', readonly=True)
    finance_approval_reason = fields.Text(
        help='Reason recorded when approving a quotation yourself, or when approving an exceptional quotation.')
    finance_approval_required = fields.Boolean(
        compute='_compute_finance_approval_required',
        compute_sudo=True,
        help=(
            'True when the current commercial terms require manager approval '
            'before Issue Offer PDF. Resolve or approve every listed exception.'
        ),
    )

    def _finance_manager(self):
        user = self.env.user
        return self._quotation_manager() or user.has_group('account.group_account_manager')

    def _quotation_manager(self):
        user = self.env.user
        return self.env.is_superuser() or user.has_group(
            'sale_order_product_pricing.quotation_manager_group'
        ) or user.has_group('sales_team.group_sale_manager')

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for incoming in vals_list:
            vals = dict(incoming)
            incoterm = self.env['account.incoterms'].browse(vals.get('incoterm'))
            safe_cif_default = bool(
                incoterm and incoterm.code == 'CIF'
                and vals.get('tax_treatment') in (None, 'cif_no_taxes')
            )
            if 'tax_treatment' in vals and not self._finance_manager() and not safe_cif_default:
                raise AccessError(_('Only Finance/Quotation Management may choose Tax Treatment.'))
            if safe_cif_default:
                vals['tax_treatment'] = 'cif_no_taxes'
            company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
            days = vals.get('offer_expiry_days', company.quotation_expiry_days_default)
            if days != company.quotation_expiry_days_default:
                if not self._finance_manager():
                    raise AccessError(_('Only Quotation, Sales, or Accounting Managers may override Days of Expiry.'))
                if not (vals.get('finance_approval_reason') or '').strip():
                    raise ValidationError(_('A stated reason is required for a Days of Expiry override.'))
            prepared.append(vals)
        orders = super().create(prepared)
        # Applies equally to UI, import and RPC creation.  Standard policy is
        # applied deliberately by Finance once its tax configuration exists;
        # CIF can safely remove product taxes immediately.
        orders.filtered(lambda order: order.tax_treatment == 'cif_no_taxes')._apply_tax_treatment()
        for order in orders.filtered(
            lambda item: item.offer_expiry_days != item.company_id.quotation_expiry_days_default
        ):
            order.message_post(body=_('Days of Expiry overridden to %(days)s by %(user)s: %(reason)s') % {
                'days': order.offer_expiry_days,
                'user': self.env.user.display_name,
                'reason': order.finance_approval_reason,
            })
        return orders

    def _finance_tax_ids(self):
        self.ensure_one()
        if self.tax_treatment == 'cif_no_taxes':
            return self.env['account.tax']
        vat_tax = self.company_id.quotation_vat_tax_id
        retention_tax = self.company_id.quotation_retention_tax_id
        if not vat_tax or not retention_tax:
            raise UserError(_(
                'Finance must configure the quotation VAT and withholding taxes before Standard VAT + Retention can be applied.'
            ))
        if vat_tax.company_id != self.company_id or retention_tax.company_id != self.company_id:
            raise ValidationError(_('Quotation taxes must belong to the quotation company.'))
        if vat_tax.type_tax_use != 'sale' or retention_tax.type_tax_use != 'sale':
            raise ValidationError(_('Quotation VAT and retention taxes must both be sales taxes.'))
        if vat_tax.amount_type != 'percent' or float_compare(vat_tax.amount, 14.0, precision_digits=4):
            raise ValidationError(_('The configured quotation VAT tax must be a 14% percentage tax.'))
        if retention_tax.amount_type != 'percent' or float_compare(retention_tax.amount, -1.0, precision_digits=4):
            raise ValidationError(_('The configured quotation retention tax must be a negative 1% percentage tax.'))
        for document_name, retention_lines in (
                ('invoice', retention_tax.invoice_repartition_line_ids),
                ('credit note', retention_tax.refund_repartition_line_ids)):
            retention_lines = retention_lines.filtered(
                lambda line: line.repartition_type == 'tax'
            )
            if not retention_lines or any(not line.account_id for line in retention_lines):
                raise ValidationError(_(
                    'The configured quotation retention tax needs a Finance-configured withholding account on every %(document)s tax repartition line.'
                ) % {'document': document_name})
            if any(not line.tag_ids for line in retention_lines):
                raise ValidationError(_(
                    'The configured quotation retention tax needs at least one tax-report tag on every %(document)s tax repartition line.'
                ) % {'document': document_name})
        return vat_tax | retention_tax

    def _apply_tax_treatment(self):
        for order in self:
            tax_ids = order._finance_tax_ids()
            lines = order.order_line.filtered(lambda line: not line.display_type)
            lines.with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({
                'tax_id': [(6, 0, tax_ids.ids)],
            })

    @api.onchange('incoterm')
    def _onchange_finance_incoterm(self):
        for order in self:
            if order.incoterm and order.incoterm.code == 'CIF':
                order.tax_treatment = 'cif_no_taxes'

    @api.onchange('tax_treatment')
    def _onchange_tax_treatment(self):
        for order in self:
            if order.tax_treatment == 'cif_no_taxes':
                tax_ids = self.env['account.tax']
            elif order.company_id.quotation_vat_tax_id and order.company_id.quotation_retention_tax_id:
                tax_ids = order.company_id.quotation_vat_tax_id | order.company_id.quotation_retention_tax_id
            else:
                continue
            for line in order.order_line.filtered(lambda item: not item.display_type):
                line.tax_id = tax_ids

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
        company = order.company_id
        # An explicitly authorized zero-price FOC line already carries its own
        # reason, actor and timestamp. Requiring a second manual-price approval
        # would make the FOC authorization unusable at issue time.
        if any(
                line.price_origin == 'edited' and not line._is_authorized_foc()
                for line in lines):
            requirements['manual_price'] = _('Manual selling price')
        assigned_caps = [
            (user.standard_discount_cap if 'standard_discount_cap' in user._fields
             else getattr(user, 'max_discount', 0.0)) or 0.0
            for user in (order.user_id | order.quotation_specialist_id)
        ]
        company_cap = (
            company.standard_discount_maximum if 'standard_discount_maximum' in company._fields
            else 30.0
        ) or 0.0
        personal_cap = min(max(assigned_caps or [0.0]), company_cap, 30.0)
        if any(
                line.standard_discount_override_used
                or line.discount > personal_cap
                for line in lines):
            requirements['discount_override'] = _('Discount override')
        if company.quotation_standard_payment_term_id and order.payment_term_id != company.quotation_standard_payment_term_id:
            requirements['nonstandard_payment_terms'] = _('Nonstandard payment terms')
        if company.quotation_standard_incoterm_id and order.incoterm != company.quotation_standard_incoterm_id:
            requirements['nonstandard_delivery_terms'] = _('Nonstandard delivery terms')
        if order.offer_expiry_days != company.quotation_expiry_days_default:
            requirements['validity_override'] = _('Validity override')
        eur = self.env.ref('base.EUR')
        order_date = fields.Date.to_date(order.date_order) or fields.Date.context_today(order)
        untaxed_eur = order.currency_id._convert(order.amount_untaxed, eur, company, order_date)
        if untaxed_eur >= 100000.0:
            requirements['high_value'] = _('Untaxed EUR-equivalent value of EUR 100,000 or more')
        return requirements

    @api.depends('order_line.price_origin', 'order_line.discount',
                 'order_line.standard_discount_override_used', 'payment_term_id', 'incoterm',
                 'offer_expiry_days', 'amount_untaxed', 'currency_id', 'finance_approval_ids.invalidated')
    def _compute_finance_approval_required(self):
        for order in self:
            order.finance_approval_required = bool(order._finance_requirement_codes())

    def _invalidate_finance_approvals(self, reason):
        # Ordinary Sales/QS users intentionally have no read ACL on protected
        # approval evidence. Commercial edits must still invalidate that
        # evidence without leaking it or failing the legitimate edit.
        approvals = self.sudo().mapped('finance_approval_ids').filtered(
            lambda approval: not approval.invalidated
        )
        if approvals:
            approvals.sudo().with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({
                'invalidated': True,
                'invalidated_reason': reason,
                'invalidated_date': fields.Datetime.now(),
            })
        if approvals:
            for order in self:
                order.message_post(body=_('Finance approvals invalidated: %s') % reason)

    def action_approve_finance_requirements(self):
        if not self._quotation_manager():
            raise AccessError(_('Only Quotation Managers and Sales Managers may approve quotation finance requirements.'))
        for order in self:
            requirements = order._finance_requirement_codes()
            self_approval = self.env.user in (order.user_id | order.quotation_specialist_id)
            if self_approval and not (order.finance_approval_reason or '').strip():
                raise ValidationError(_('A stated reason is required for self-approval.'))
            current = order.finance_approval_ids.filtered(lambda approval: not approval.invalidated)
            approved_codes = set(current.mapped('code'))
            for code, label in requirements.items():
                if code not in approved_codes:
                    self.env['sale.order.finance.approval'].sudo().with_context(
                        _finance_internal_token=_FINANCE_INTERNAL_TOKEN
                    ).create({
                        'order_id': order.id,
                        'code': code,
                        'label': label,
                        'approver_id': self.env.user.id,
                        'reason': order.finance_approval_reason or _('Manager approval.'),
                    })
            order.message_post(body=_('Finance requirements approved by %s.') % self.env.user.display_name)
        return True

    def _check_finance_issue_requirements(self):
        """Authoritative Issue Offer PDF gate; lifecycle code calls this before rendering."""
        for order in self:
            commercial_lines = order.order_line.filtered(lambda line: not line.display_type)
            incomplete_lines = commercial_lines.filtered(
                lambda line: getattr(line, 'is_add_below_placeholder', False)
                or not line.product_id or not line.product_uom
            )
            if incomplete_lines:
                raise UserError(_(
                    'Issue Offer PDF is blocked: complete or remove every blank Add Below product row.'
                ))
            if order.tax_treatment == 'standard':
                tax_ids = order._finance_tax_ids()
                if any(line.tax_id != tax_ids for line in commercial_lines):
                    raise UserError(_(
                        'Issue Offer PDF is blocked: every commercial line must use the configured Standard VAT and Retention taxes.'
                    ))
            elif any(line.tax_id for line in commercial_lines):
                raise UserError(_(
                    'Issue Offer PDF is blocked: CIF - No Taxes quotations cannot carry line taxes.'
                ))
            zero_price_lines = order.order_line.filtered(
                lambda line: not line.display_type and float_compare(
                    line.price_unit, 0.0, precision_rounding=order.currency_id.rounding
                ) == 0
            )
            unauthorised = zero_price_lines.filtered(
                lambda line: not line._is_authorized_foc()
            )
            if unauthorised:
                raise UserError(_(
                    'Issue Offer PDF is blocked: every zero-price line must be marked Free of Charge with a reason by an authorized Pricing User, Quotation Manager, or Sales Manager.'
                ))
            requirements = order._finance_requirement_codes()
            approved = set(order.sudo().finance_approval_ids.filtered(
                lambda approval: not approval.invalidated
            ).mapped('code'))
            missing = [label for code, label in requirements.items() if code not in approved]
            if missing:
                raise UserError(_('Issue Offer PDF requires approval for: %s.') % ', '.join(missing))
        return True

    def write(self, vals):
        if _is_finance_internal(self.env) or _is_offer_date_internal(self.env):
            return super().write(vals)
        vals = dict(vals)
        previous_treatments = {order.id: order.tax_treatment for order in self}
        incoming_incoterm = self.env['account.incoterms'].browse(vals.get('incoterm'))
        safe_cif_default = bool(
            incoming_incoterm and incoming_incoterm.code == 'CIF'
            and vals.get('tax_treatment') in (None, 'cif_no_taxes')
        )
        if safe_cif_default:
            # Selecting CIF always takes the safe no-tax default, including
            # RPC/import. Finance may deliberately change the treatment later.
            vals['tax_treatment'] = 'cif_no_taxes'
        if 'tax_treatment' in vals and not self._finance_manager() and not safe_cif_default:
            raise AccessError(_('Only Finance/Quotation Management may change Tax Treatment.'))
        expiry_changes = self.filtered(
            lambda order: 'offer_expiry_days' in vals and
            vals['offer_expiry_days'] != order.offer_expiry_days
        )
        if expiry_changes:
            if not self._finance_manager():
                raise AccessError(_('Only Quotation, Sales, or Accounting Managers may override Days of Expiry.'))
            for order in expiry_changes.filtered(
                lambda item: vals['offer_expiry_days'] != item.company_id.quotation_expiry_days_default
            ):
                reason = vals.get('finance_approval_reason', order.finance_approval_reason)
                if not (reason or '').strip():
                    raise ValidationError(_('A stated reason is required for a Days of Expiry override.'))
        relevant = {'tax_treatment', 'payment_term_id', 'incoterm', 'offer_expiry_days',
                    'currency_id', 'order_line'} & set(vals)
        result = super().write(vals)
        if 'tax_treatment' in vals:
            self._apply_tax_treatment()
            labels = dict(self._fields['tax_treatment'].selection)
            for order in self.filtered(
                    lambda item: previous_treatments[item.id] != item.tax_treatment):
                order.message_post(body=_(
                    'Tax Treatment changed from %(old)s to %(new)s by %(user)s.'
                ) % {
                    'old': labels.get(previous_treatments[order.id], previous_treatments[order.id]),
                    'new': labels.get(order.tax_treatment, order.tax_treatment),
                    'user': self.env.user.display_name,
                })
        if relevant:
            self._invalidate_finance_approvals(_('Commercial header changed.'))
        for order in expiry_changes.filtered(
            lambda item: vals['offer_expiry_days'] != item.company_id.quotation_expiry_days_default
        ):
            order.message_post(body=_('Days of Expiry overridden to %(days)s by %(user)s: %(reason)s') % {
                'days': vals['offer_expiry_days'],
                'user': self.env.user.display_name,
                'reason': vals.get('finance_approval_reason', order.finance_approval_reason),
            })
        return result

    def _prepare_invoice(self):
        self.ensure_one()
        values = super()._prepare_invoice()
        values.update({
            'quotation_tax_treatment': self.tax_treatment,
            'quotation_retention_tax_id': (
                self.company_id.quotation_retention_tax_id.id
                if self.tax_treatment == 'standard' else False
            ),
        })
        return values


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @staticmethod
    def _uses_controlled_tax_policy(order):
        """Keep standard Odoo tax behavior until Finance enables this policy."""
        return bool(
            order and (
                order.tax_treatment == 'cif_no_taxes'
                or (
                    order.company_id.quotation_vat_tax_id
                    and order.company_id.quotation_retention_tax_id
                )
            )
        )

    is_free_of_charge = fields.Boolean(string='Free of Charge', copy=True,
                                        help='Authorized exception for a zero selling-price line.')
    free_of_charge_reason = fields.Text(
        string='Free of Charge Reason', copy=True,
        help=(
            'Required business reason for an authorized zero-price line. '
            'Pricing or quotation management records it before Issue Offer PDF.'
        ),
    )
    free_of_charge_authorized_by = fields.Many2one('res.users', readonly=True, copy=False)
    free_of_charge_authorized_at = fields.Datetime(readonly=True, copy=False)

    def _is_authorized_foc(self):
        self.ensure_one()
        return bool(
            float_compare(
                self.price_unit, 0.0,
                precision_rounding=self.order_id.currency_id.rounding,
            ) == 0
            and self.is_free_of_charge
            and (self.free_of_charge_reason or '').strip()
            and self.free_of_charge_authorized_by
            and self.free_of_charge_authorized_at
        )

    def _can_authorize_foc(self):
        user = self.env.user
        return self.env.is_superuser() or user.has_group(
            'sale_order_product_pricing.product_pricing_group'
        ) or user.has_group('sale_order_product_pricing.quotation_manager_group') or user.has_group(
            'sales_team.group_sale_manager'
        )

    def _check_free_of_charge_authorization(self, vals):
        if vals.get('is_free_of_charge') and not self._can_authorize_foc():
            raise AccessError(_('Only an authorized Pricing User, Quotation Manager, or Sales Manager may mark a line Free of Charge.'))
        for line in self:
            foc = vals.get('is_free_of_charge', line.is_free_of_charge)
            reason = vals.get('free_of_charge_reason', line.free_of_charge_reason)
            if foc and not (reason or '').strip():
                raise ValidationError(_('A Free of Charge reason is required.'))

    @api.model_create_multi
    def create(self, vals_list):
        if not _is_finance_internal(self.env):
            for vals in vals_list:
                if {'free_of_charge_authorized_by', 'free_of_charge_authorized_at'}.intersection(vals):
                    raise AccessError(_('Free of Charge authorization evidence is system-managed.'))
                order = self.env['sale.order'].browse(vals.get('order_id')).exists()
                if 'tax_id' in vals and self._uses_controlled_tax_policy(order):
                    # Product onchange/import values cannot select a tax policy.
                    # The header applies the configured taxes below instead.
                    vals.pop('tax_id')
                if vals.get('is_free_of_charge'):
                    if not self._can_authorize_foc():
                        raise AccessError(_('Only an authorized Pricing User, Quotation Manager, or Sales Manager may mark a line Free of Charge.'))
                    if not (vals.get('free_of_charge_reason') or '').strip():
                        raise ValidationError(_('A Free of Charge reason is required.'))
            vals_list = [dict(vals, **(
                {'free_of_charge_authorized_by': self.env.user.id,
                 'free_of_charge_authorized_at': fields.Datetime.now()}
                if vals.get('is_free_of_charge') else {}
            )) for vals in vals_list]
        lines = super().create(vals_list)
        if not _is_finance_internal(self.env):
            for order in lines.mapped('order_id'):
                configured_standard = (
                    order.company_id.quotation_vat_tax_id and
                    order.company_id.quotation_retention_tax_id
                )
                if order.tax_treatment == 'cif_no_taxes' or configured_standard:
                    tax_ids = order._finance_tax_ids()
                    lines.filtered(lambda line: line.order_id == order and not line.display_type).with_context(
                        _finance_internal_token=_FINANCE_INTERNAL_TOKEN
                    ).write({'tax_id': [(6, 0, tax_ids.ids)]})
        return lines

    def write(self, vals):
        if not _is_finance_internal(self.env):
            if {'free_of_charge_authorized_by', 'free_of_charge_authorized_at'}.intersection(vals):
                raise AccessError(_('Free of Charge authorization evidence is system-managed.'))
            if 'tax_id' in vals and any(
                    self._uses_controlled_tax_policy(order)
                    for order in self.mapped('order_id')):
                raise UserError(_('Direct line-tax edits are restricted. Change Tax Treatment on the quotation header.'))
            if {'is_free_of_charge', 'free_of_charge_reason'}.intersection(vals) and not self._can_authorize_foc():
                raise AccessError(_('Only an authorized Pricing User, Quotation Manager, or Sales Manager may change Free of Charge details.'))
            self._check_free_of_charge_authorization(vals)
            if vals.get('is_free_of_charge'):
                vals.update({
                    'free_of_charge_authorized_by': self.env.user.id,
                    'free_of_charge_authorized_at': fields.Datetime.now(),
                })
        result = super().write(vals)
        if not _is_finance_internal(self.env) and ({'price_unit', 'discount', 'discount_2', 'discount_3',
                                                     'purchase_price_estimate', 'is_free_of_charge',
                                                     'free_of_charge_reason'} & set(vals)):
            self.mapped('order_id')._invalidate_finance_approvals(_('Commercial line changed.'))
        return result


class AccountMove(models.Model):
    _inherit = 'account.move'

    quotation_tax_treatment = fields.Selection([
        ('standard', 'Standard VAT 14% + Retention 1%'),
        ('cif_no_taxes', 'CIF - No Taxes'),
    ], copy=True, readonly=True)
    quotation_retention_tax_id = fields.Many2one('account.tax', readonly=True, copy=True)
    quotation_retention_basis = fields.Monetary(compute='_compute_quotation_retention', store=True)
    quotation_retention_amount = fields.Monetary(compute='_compute_quotation_retention', store=True)

    @api.depends('amount_untaxed', 'quotation_retention_tax_id', 'move_type')
    def _compute_quotation_retention(self):
        for move in self:
            refund_sign = -1.0 if move.move_type in ('out_refund', 'in_refund') else 1.0
            basis = (
                refund_sign * move.amount_untaxed
                if move.quotation_retention_tax_id else 0.0
            )
            move.quotation_retention_basis = move.currency_id.round(basis)
            retention_amount = (
                basis * (move.quotation_retention_tax_id.amount / 100.0)
                if move.quotation_retention_tax_id and move.quotation_retention_tax_id.amount_type == 'percent'
                else 0.0
            )
            move.quotation_retention_amount = move.currency_id.round(retention_amount)
