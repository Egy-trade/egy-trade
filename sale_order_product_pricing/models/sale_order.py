"""Controlled quotation pricing based on canonical ``sale.order.line`` records.

The historical Product Pricing grid used a second writable representation of a
quotation. It is retired: all pricing state and mutations live on canonical sale
order lines.
"""

import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


_PRICING_INTERNAL_TOKEN = object()
_PRICING_DOWNPAYMENT_TOKEN = object()
_PRICING_RECLASSIFY_TOKEN = object()
_PRICING_ORDER_RECOMPUTE_TOKEN = object()


def _is_pricing_internal(env):
    """Return true only for in-process calls carrying our unforgeable token."""
    return env.context.get('_pricing_internal_token') is _PRICING_INTERNAL_TOKEN


def _is_pricing_downpayment(env):
    """Identify down-payment lines created by the standard Odoo wizard."""
    return env.context.get('_pricing_downpayment_token') is _PRICING_DOWNPAYMENT_TOKEN


def _is_pricing_reclassification(env):
    """Identify the narrowly scoped manager provenance-certification operation."""
    return env.context.get('_pricing_reclassify_token') is _PRICING_RECLASSIFY_TOKEN


def _is_pricing_order_recompute(env):
    """Identify an in-process customer/date onchange price recomputation."""
    return env.context.get(
        '_pricing_order_recompute_token'
    ) is _PRICING_ORDER_RECOMPUTE_TOKEN


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # A UI alias only: order_line remains the single source of truth for
    # pricing, revisions and reporting. This separate field name prevents
    # the restricted pricing tree from colliding with live Order Lines.
    pricing_line_ids = fields.One2many(
        'sale.order.line', 'order_id', string='Pricing Lines',
        domain=[('display_type', '=', False), ('is_downpayment', '=', False)],
        copy=False,
        groups='sale_order_product_pricing.product_pricing_group',
        help='Restricted workspace over the same quotation lines shown on Order Lines.',
    )
    product_pricing = fields.Boolean(
        copy=True, groups='sale_order_product_pricing.product_pricing_group',
        help='Enable the controlled Purchase Price Estimate preview and Apply workflow.')
    total_estimate_unit_price = fields.Float(
        compute='_compute_estimate_unit_price',
        groups='sale_order_product_pricing.product_pricing_group')
    currency_estimate_id = fields.Many2one(
        'res.currency', string='Purchase Currency', copy=True,
        default=lambda self: self.env.company.currency_id,
        help='Currency used for Purchase Price Estimates before conversion to the quotation currency.',
        groups='sale_order_product_pricing.product_pricing_group')
    currency_estimate_id_symbol = fields.Char(
        related='currency_estimate_id.symbol',
        groups='sale_order_product_pricing.product_pricing_group')
    currency_rate_estimate = fields.Float(
        compute='_compute_currency_rate', digits=(12, 6), copy=True, store=True,
        help='Exchange rate used to convert Purchase Price Estimates into the quotation currency.',
        groups='sale_order_product_pricing.product_pricing_group')
    currency_rate_inverse = fields.Float(
        compute='_compute_currency_rate_inverse', digits=(12, 6), store=True,
        help='Inverse exchange rate displayed for review.',
        groups='sale_order_product_pricing.product_pricing_group')
    change_currency_rate_type = fields.Selection(
        [('amount', 'Amount'), ('percentage', 'Percentage')], copy=True,
        help='Choose whether the exchange-rate adjustment is a fixed amount or percentage.',
        groups='sale_order_product_pricing.product_pricing_group')
    change_currency_rate = fields.Float(
        copy=True,
        help='Adjustment applied to the exchange rate used by Product Pricing.',
        groups='sale_order_product_pricing.product_pricing_group')
    global_factor = fields.Float(
        default=1.0, copy=True,
        help='Default multiplier applied to eligible lines in the Product Pricing preview.',
        groups='sale_order_product_pricing.product_pricing_group')
    analysis_created = fields.Boolean(copy=False)
    product_pricing_preview_hash = fields.Char(
        copy=False, readonly=True,
        groups='sale_order_product_pricing.product_pricing_group')
    product_pricing_previewed_at = fields.Datetime(
        copy=False, readonly=True,
        groups='sale_order_product_pricing.product_pricing_group')
    pricing_audit_log_ids = fields.One2many(
        'sale.order.pricing.audit', 'order_id', string='Pricing Log', readonly=True,
        copy=False, groups='sale_order_product_pricing.product_pricing_group')

    @api.onchange('global_factor')
    def _onchange_global_factor(self):
        """Stage factor changes only; selling prices change exclusively on Apply."""
        for order in self:
            order._pricing_lines().factor = order.global_factor

    def write(self, vals):
        currency_changed = bool({'currency_id', 'pricelist_id'} & set(vals))
        order_price_recompute = bool({'partner_id', 'date_order'} & set(vals))
        previous_currencies = {}
        previous_prices = {}
        if currency_changed:
            previous_currencies = {order.id: order.currency_id.display_name for order in self}
            previous_prices = {
                line.id: (
                    line.price_unit,
                    line.sudo().price_origin,
                    line.sudo().price_currency_id,
                )
                for order in self for line in order._pricing_lines()
            }
        write_target = self.with_context(
            _pricing_order_recompute_token=_PRICING_ORDER_RECOMPUTE_TOKEN,
        ) if order_price_recompute else self
        result = super(SaleOrder, write_target).write(vals)
        if 'global_factor' in vals and not _is_pricing_internal(self.env):
            for order in self:
                order._pricing_lines().with_context(
                    _pricing_internal_token=_PRICING_INTERNAL_TOKEN
                ).write({'factor': order.global_factor})
        if currency_changed and not _is_pricing_internal(self.env):
            for order in self:
                for line in order._pricing_lines():
                    old_price, old_origin, old_currency = previous_prices[line.id]
                    protected_line = line.sudo()
                    if (protected_line.price_origin == 'pricelist'
                            and protected_line.price_origin_verified):
                        pricelist_price = line._pricing_pricelist_price()
                        protected_line.with_context(
                            _pricing_internal_token=_PRICING_INTERNAL_TOKEN
                        ).write({
                            'price_unit': pricelist_price,
                            'price_reference': pricelist_price,
                            'price_origin': 'pricelist',
                            'price_origin_verified': True,
                            'price_origin_evidence': 'new_pricelist',
                            'price_currency_id': order.currency_id.id,
                        })
                        reason = _('Currency/pricelist changed from %(old)s [%(old_id)s] to %(new)s [%(new_id)s]; '
                                   'Odoo Price List refreshed.') % {
                            'old': previous_currencies[order.id], 'old_id': old_currency.id,
                            'new': order.currency_id.display_name, 'new_id': order.currency_id.id,
                        }
                    elif protected_line.pricing_reprice_pending:
                        reason = _('Currency/pricelist changed from %(old)s [%(old_id)s] to %(new)s [%(new_id)s]; '
                                   'the pending product/UoM replacement will be repriced by confirmed Apply.') % {
                            'old': old_currency.display_name or previous_currencies[order.id],
                            'old_id': old_currency.id, 'new': order.currency_id.display_name,
                            'new_id': order.currency_id.id,
                        }
                    elif protected_line.price_origin == 'edited':
                        reason = _('Currency/pricelist changed from %(old)s [%(old_id)s] to %(new)s [%(new_id)s]; '
                                   'Edited amount remains '
                                   'unchanged until the confirmed conversion preview is applied.') % {
                            'old': old_currency.display_name or previous_currencies[order.id],
                            'old_id': old_currency.id, 'new': order.currency_id.display_name,
                            'new_id': order.currency_id.id,
                        }
                    else:
                        reason = _('Currency/pricelist changed from %(old)s [%(old_id)s] to %(new)s [%(new_id)s]; '
                                   'Product Pricing remains '
                                   'unchanged until the confirmed preview is applied.') % {
                            'old': old_currency.display_name or previous_currencies[order.id],
                            'old_id': old_currency.id, 'new': order.currency_id.display_name,
                            'new_id': order.currency_id.id,
                        }
                    order._pricing_log_line(
                        line, reason, old_price=old_price, old_origin=old_origin,
                        old_currency=old_currency)
        return result

    @api.depends('order_line.estimate_unit_price')
    def _compute_estimate_unit_price(self):
        for order in self:
            order.total_estimate_unit_price = sum(order.order_line.mapped('estimate_unit_price'))

    @api.onchange('change_currency_rate_type', 'change_currency_rate')
    @api.constrains('change_currency_rate')
    def check_currency_rate_type(self):
        for order in self:
            if order.change_currency_rate_type == 'percentage' and order.change_currency_rate > 100:
                raise ValidationError(_('The currency-rate adjustment cannot exceed 100%.'))

    @api.depends('currency_id', 'currency_estimate_id', 'date_order', 'company_id')
    def _compute_currency_rate(self):
        for order in self:
            date = fields.Date.to_date(order.date_order) or fields.Date.context_today(order)
            company_currency = order.company_id.currency_id
            if not company_currency or not order.currency_estimate_id:
                order.currency_rate_estimate = 1.0
                continue
            order.currency_rate_estimate = self.env['res.currency']._get_conversion_rate(
                company_currency, order.currency_estimate_id, order.company_id, date)

    @api.depends('currency_id', 'currency_estimate_id', 'date_order', 'company_id')
    def _compute_currency_rate_inverse(self):
        for order in self:
            date = fields.Date.to_date(order.date_order) or fields.Date.context_today(order)
            if not order.currency_estimate_id or not order.currency_id:
                order.currency_rate_inverse = 1.0
            else:
                order.currency_rate_inverse = self.env['res.currency']._get_conversion_rate(
                    order.currency_estimate_id, order.currency_id, order.company_id, date)

    def _pricing_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: not line.display_type and not line.is_downpayment)

    def _pricing_preview_payload(self):
        """Return a serializable preview without changing quotation prices."""
        self.ensure_one()
        lines = []
        for line in self._pricing_lines():
            item = {
                'line_id': line.id,
                'product_id': line.product_id.id,
                'product_name': line.product_id.display_name,
                'product_uom_id': line.product_uom.id,
                'quantity': line.product_uom_qty,
                'purchase_cost': line.purchase_price_estimate,
                'cost_currency_id': line.currency_estimate_id.id,
                'factor': line.factor,
                'line_factor': line.line_factor,
                'currency_rate': line.currency_rate_estimate,
                'partner_id': self.partner_id.id,
                'pricelist_id': self.pricelist_id.id,
                'current_price': line.price_unit,
                'reference_price': line.price_reference,
                'origin': line.price_origin,
                'reprice_pending': line.pricing_reprice_pending,
                'price_currency_id': line.price_currency_id.id,
                'proposed_currency_id': self.currency_id.id,
            }
            if not line.product_id:
                item.update(status='blocked', reason=_('A product is required.'))
            elif line.purchase_price_estimate < 0:
                item.update(status='blocked', reason=_('Purchasing cost cannot be negative.'))
            elif not line.purchase_price_estimate:
                proposed_price = line._pricing_pricelist_price()
                item.update(
                    status='skipped', origin='pricelist',
                    proposed_price=proposed_price,
                    reprice_required=(
                        line.pricing_reprice_pending
                        or line.price_unit != proposed_price
                        or line.price_reference != proposed_price
                        or line.price_currency_id != self.currency_id
                    ),
                    reason=_('No purchasing cost: Product Pricing is skipped and Odoo Price List remains in use.'))
            elif line.factor <= 0 or line.line_factor <= 0 or line.currency_rate_estimate <= 0:
                item.update(status='blocked', reason=_('Factor, line factor, and currency rate must all be positive.'))
            elif line.pricing_reprice_pending:
                item.update(
                    status='ready', proposed_price=line._pricing_target_price(),
                    reason=_('Product, UoM, or quantity changed: the line will be repriced by the confirmed Apply.'))
            elif line.price_origin == 'edited':
                proposed_price = line._pricing_convert_price(
                    line.price_unit, line.price_currency_id, self.currency_id)
                item.update(
                    status='protected', proposed_price=proposed_price,
                    conversion_required=line.price_currency_id != self.currency_id,
                    reason=_('Edited selling price is protected; preview shows conversion only when its stored '
                             'price currency differs from the quotation currency.'))
            else:
                item.update(status='ready', proposed_price=line._pricing_target_price())
            lines.append(item)
        return lines

    def _pricing_preview_hash(self, preview):
        """Bind Apply to the exact reviewed pricing inputs, not merely a timestamp."""
        payload = [
            (item['line_id'], item['product_id'], item.get('product_uom_id'), item.get('quantity'),
             item.get('purchase_cost'), item.get('cost_currency_id'), item.get('factor'),
             item.get('line_factor'), item.get('currency_rate'), item.get('partner_id'),
             item.get('pricelist_id'), item['current_price'], item['reference_price'], item['origin'],
             item.get('reprice_pending'), item.get('price_currency_id'),
             item.get('proposed_currency_id'),
             item.get('proposed_price'), item.get('conversion_required'),
             item.get('reprice_required'), item['status'])
            for item in preview
        ]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def get_product_pricing_preview(self):
        """RPC-safe detailed preview for a future wizard/client action."""
        self.ensure_one()
        preview = self._pricing_preview_payload()
        return {'lines': preview, 'hash': self._pricing_preview_hash(preview)}

    def action_preview_product_pricing(self):
        """Open a line-by-line review dialog without changing quotation prices."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Product Pricing is available only on a draft quotation.'))
        if not self.product_pricing:
            raise UserError(_('Enable Product Pricing before previewing this quotation.'))
        preview = self._pricing_preview_payload()
        if not preview:
            raise UserError(_('Add at least one quotation line before previewing Product Pricing.'))
        preview_hash = self._pricing_preview_hash(preview)
        self.with_context(_pricing_internal_token=_PRICING_INTERNAL_TOKEN).write({
            'product_pricing_preview_hash': preview_hash,
            'product_pricing_previewed_at': fields.Datetime.now(),
        })
        counts = {}
        for item in preview:
            counts[item['status']] = counts.get(item['status'], 0) + 1
        wizard_lines = []
        for item in preview:
            line = self.env['sale.order.line'].browse(item['line_id'])
            wizard_lines.append((0, 0, {
                'sale_line_id': line.id,
                'product_id': line.product_id.id,
                'product_uom_id': line.product_uom.id,
                'quantity': item['quantity'],
                'purchase_cost': item['purchase_cost'],
                'cost_currency_id': item['cost_currency_id'],
                'factor': item['factor'],
                'line_factor': item['line_factor'],
                'currency_rate': item['currency_rate'],
                'status': item['status'],
                'origin': item['origin'],
                'current_price': item['current_price'],
                'proposed_price': item.get('proposed_price', item['current_price']),
                'current_currency_id': (line.price_currency_id or self.currency_id).id,
                'proposed_currency_id': self.currency_id.id,
                'reason': item.get('reason'),
                'conversion_required': item.get('conversion_required', False),
                'reprice_required': item.get('reprice_required', False),
            }))
        wizard = self.env['sale.order.pricing.preview'].create({
            'order_id': self.id,
            'preview_hash': preview_hash,
            'ready_count': counts.get('ready', 0),
            'protected_count': counts.get('protected', 0),
            'skipped_count': counts.get('skipped', 0),
            'blocked_count': counts.get('blocked', 0),
            'can_apply': not counts.get('blocked', 0),
            'line_ids': wizard_lines,
        })
        self._pricing_log(_(
            'Product Pricing preview created: %(ready)s ready, %(protected)s Edited protected, '
            '%(skipped)s skipped, %(blocked)s blocked.') % {
                'ready': counts.get('ready', 0),
                'protected': counts.get('protected', 0),
                'skipped': counts.get('skipped', 0),
                'blocked': counts.get('blocked', 0),
            })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Product Pricing Preview'),
            'res_model': 'sale.order.pricing.preview',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply_product_pricing(self):
        """Apply a previously reviewed, unchanged, complete pricing proposal atomically.

        A view/wizard must explicitly pass ``pricing_apply_confirmed`` after the
        user has reviewed :meth:`action_preview_product_pricing`.
        """
        for order in self:
            if order.state != 'draft':
                raise UserError(_('Product Pricing is available only on a draft quotation.'))
            if not order.product_pricing:
                raise UserError(_('Enable Product Pricing before applying this quotation.'))
            if not self.env.context.get('pricing_apply_confirmed'):
                raise UserError(_('Preview Product Pricing first, then confirm Apply.'))
            preview = order._pricing_preview_payload()
            if not order.product_pricing_previewed_at or (
                    order.product_pricing_preview_hash != order._pricing_preview_hash(preview)):
                raise UserError(_('Pricing inputs changed since the last preview. Preview again before applying.'))
            blocked = [item for item in preview if item['status'] == 'blocked']
            if blocked:
                raise UserError(_('Product Pricing cannot be applied while an eligible line is incomplete.'))
            # All validation is complete before the first line is written. Odoo's
            # transaction then makes the multi-line operation atomic on errors.
            for item in preview:
                line = self.env['sale.order.line'].browse(item['line_id'])
                if item['status'] == 'ready':
                    line.with_context(_pricing_internal_token=_PRICING_INTERNAL_TOKEN).write({
                        'price_unit': item['proposed_price'],
                        'price_reference': item['proposed_price'],
                        'price_origin': 'product_pricing',
                        'price_origin_verified': True,
                        'price_origin_evidence': 'product_pricing_apply',
                        'price_currency_id': order.currency_id.id,
                        'pricing_reprice_pending': False,
                    })
                    order._pricing_log_line(
                        line, _(
                            'Applied confirmed Product Pricing preview: cost %(cost)s, factor %(factor)s, '
                            'line factor %(line_factor)s, currency rate %(rate)s.'
                        ) % {
                            'cost': item['purchase_cost'], 'factor': item['factor'],
                            'line_factor': item['line_factor'], 'rate': item['currency_rate'],
                        },
                        old_price=item['current_price'], old_origin=item['origin'])
                elif item['status'] == 'protected' and item.get('conversion_required'):
                    source_currency = line.price_currency_id
                    converted_reference = line._pricing_convert_price(
                        line.price_reference, line.price_currency_id, order.currency_id)
                    line.with_context(_pricing_internal_token=_PRICING_INTERNAL_TOKEN).write({
                        'price_unit': item['proposed_price'],
                        'price_reference': converted_reference,
                        'price_origin': 'edited',
                        'price_origin_verified': True,
                        'price_origin_evidence': 'manual_edit',
                        'price_currency_id': order.currency_id.id,
                        'pricing_reprice_pending': False,
                    })
                    order._pricing_log_line(
                        line,
                        _('Applied confirmed currency conversion of protected Edited price '
                          '[%(old_id)s to %(new_id)s].') % {
                            'old_id': source_currency.id, 'new_id': order.currency_id.id,
                        },
                        old_price=item['current_price'], old_origin=item['origin'],
                        old_currency=source_currency)
                elif item['status'] == 'skipped' and item.get('reprice_required'):
                    source_currency = line.price_currency_id
                    line.with_context(_pricing_internal_token=_PRICING_INTERNAL_TOKEN).write({
                        'price_unit': item['proposed_price'],
                        'price_reference': item['proposed_price'],
                        'price_origin': 'pricelist',
                        'price_origin_verified': True,
                        'price_origin_evidence': 'new_pricelist',
                        'price_currency_id': order.currency_id.id,
                        'pricing_reprice_pending': False,
                    })
                    order._pricing_log_line(
                        line,
                        _('Product Pricing skipped; confirmed Odoo Price List reprice applied.'),
                        old_price=item['current_price'], old_origin=item['origin'],
                        old_currency=source_currency)
            order._pricing_log(_(
                'Confirmed Product Pricing Apply completed; ordinary Edited prices remained protected.'
            ))
            order.with_context(_pricing_internal_token=_PRICING_INTERNAL_TOKEN).write({
                'product_pricing_preview_hash': False,
                'product_pricing_previewed_at': False,
            })
        return True

    def apply_estimate_product_price(self):
        """Backward-compatible action name; still enforces preview + confirmation."""
        return self.action_apply_product_pricing()

    def _pricing_log(self, body):
        """Create a protected pricing audit entry without exposing it in chatter."""
        for order in self:
            self.env['sale.order.pricing.audit'].sudo().create({
                'order_id': order.id,
                'reason': body,
                'user_id': self.env.user.id,
                'old_currency_id': order.currency_id.id,
                'new_currency_id': order.currency_id.id,
            })

    def _pricing_log_line(
            self, line, reason, old_price=None, old_origin=None, old_currency=None):
        """Append a protected, line-level pricing audit event."""
        self.ensure_one()
        protected_line = line.sudo()
        old_price = line.price_unit if old_price is None else old_price
        old_origin = protected_line.price_origin if old_origin is None else old_origin
        old_currency = old_currency or protected_line.price_currency_id or self.currency_id
        self.env['sale.order.pricing.audit'].sudo().create({
            'order_id': self.id,
            'line_id': line.id,
            'product_id': line.product_id.id,
            'old_price': old_price,
            'new_price': line.price_unit,
            'old_origin': old_origin or False,
            'new_origin': protected_line.price_origin,
            'old_currency_id': old_currency.id,
            'new_currency_id': (protected_line.price_currency_id or self.currency_id).id,
            'reason': reason,
            'user_id': self.env.user.id,
        })


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    purchase_price_estimate = fields.Float(
        string='Purchase Price Estimate', copy=True,
        help='Estimated supplier purchase price used only for quotation pricing. It is not the Accounting Cost.',
        groups='sale_order_product_pricing.product_pricing_group')
    factor = fields.Float(
        copy=True, groups='sale_order_product_pricing.product_pricing_group',
        help='Order-level multiplier copied to this line for the pricing formula.')
    line_factor = fields.Float(
        default=1.0, copy=True,
        groups='sale_order_product_pricing.product_pricing_group',
        help='Additional line-specific multiplier used by the pricing formula.')
    qty_estimate = fields.Float(
        string='Quantity', default=1.0,
        help='Quotation quantity mirrored for the internal pricing worksheet.')
    estimate_unit_price = fields.Float(
        string='Estimated Unit Price', compute='_compute_estimate_unit_price', store=True,
        help='Preview formula result before it is applied to Unit Price.',
        groups='sale_order_product_pricing.product_pricing_group')
    currency_estimate_id = fields.Many2one(
        'res.currency', compute='_compute_currency_estimate',
        groups='sale_order_product_pricing.product_pricing_group')
    currency_rate_estimate = fields.Float(
        compute='_compute_currency_rate_estimate', store=True,
        help='Conversion rate used by the Product Pricing formula.',
        groups='sale_order_product_pricing.product_pricing_group')
    note = fields.Char(help='Internal note for this Product Pricing line.')
    price_origin = fields.Selection(
        [('product_pricing', 'Product Pricing'),
         ('pricelist', 'Odoo Pricelist'),
         ('edited', 'Manual Price'),
         ('historical_unverified', 'Historical—Unverified')],
        default='pricelist', required=True, copy=True, index=True,
        groups='sale_order_product_pricing.product_pricing_group')
    price_origin_verified = fields.Boolean(
        string='Price Origin Verified', default=False, copy=True, index=True,
        help='True only when system evidence proves the displayed price origin.',
        groups='sale_order_product_pricing.product_pricing_group')
    price_origin_evidence = fields.Selection(
        [('new_pricelist', 'New Odoo Pricelist Line'),
         ('product_pricing_apply', 'Confirmed Product Pricing Apply'),
         ('manual_edit', 'Authorized Manual Price Edit'),
         ('legacy_formula', 'Legacy Formula Match'),
         ('manager_reclassified', 'Manager Reclassification'),
         ('legacy_unverified', 'Legacy Origin Unverified')],
        string='Origin Evidence', copy=True, index=True,
        groups='sale_order_product_pricing.product_pricing_group')
    price_origin_label = fields.Char(
        string='Price Origin', compute='_compute_price_origin_label', compute_sudo=True,
        help='How Unit Price was established. Historical—Unverified means the old data did not prove its source.')
    price_reference = fields.Float(
        string='Reference Price', digits='Product Price', copy=True,
        help='Last verified automatic price baseline. Manual selling prices do not overwrite it.',
        groups='sale_order_product_pricing.product_pricing_group')
    price_currency_id = fields.Many2one(
        'res.currency', string='Selling Price Currency', copy=True, readonly=True,
        help='Currency of the numeric selling price and reference baseline.',
        groups='sale_order_product_pricing.product_pricing_group')
    pricing_eligible = fields.Boolean(
        compute='_compute_pricing_eligible', store=True,
        help='Eligible when Purchase Price Estimate is positive and pricing inputs are complete.',
        groups='sale_order_product_pricing.product_pricing_group')
    pricing_warning = fields.Char(
        copy=False, readonly=True,
        help='Explains the current pricing problem and the action required to resolve it.',
        groups='sale_order_product_pricing.product_pricing_group')
    pricing_reprice_pending = fields.Boolean(
        copy=False, readonly=True,
        help='Set when a product, UoM, or quantity change must be repriced by confirmed Apply.',
        groups='sale_order_product_pricing.product_pricing_group')

    @api.depends('price_origin', 'price_origin_verified')
    def _compute_price_origin_label(self):
        labels = {
            'product_pricing': _('Product Pricing'),
            'pricelist': _('Odoo Pricelist'),
            'edited': _('Manual Price'),
            'historical_unverified': _('Historical—Unverified'),
        }
        for line in self:
            line.price_origin_label = (
                labels.get(line.price_origin, _('Historical—Unverified'))
                if line.price_origin_verified else _('Historical—Unverified')
            )

    @api.model_create_multi
    def create(self, vals_list):
        # A quotation revision is an exact in-process copy.  The caller carries
        # the unforgeable pricing token, so preserve the copied origin,
        # reference, currency, cost, and factors instead of treating its lines
        # as newly keyed public input.
        if _is_pricing_internal(self.env):
            return super().create(vals_list)

        prepared_vals = []
        pricing_defaults = []
        can_manage_pricing = self.env.is_superuser() or self.env.user.has_group(
            'sale_order_product_pricing.product_pricing_group')
        for values in vals_list:
            values = dict(values)
            if values.get('purchase_price_estimate', 0) < 0:
                raise ValidationError(_('Purchasing cost cannot be negative.'))
            if values.get('is_downpayment') and not _is_pricing_downpayment(self.env):
                values['is_downpayment'] = False
            order = self.env['sale.order'].browse(values.get('order_id'))
            protected_order = order.sudo()
            requested_factor = values.pop('factor', None)
            factor = protected_order.global_factor
            if can_manage_pricing and requested_factor is not None:
                factor = requested_factor
            incoming_price = values.get('price_unit')
            values.pop('price_origin', None)
            values.pop('price_origin_verified', None)
            values.pop('price_origin_evidence', None)
            values.pop('price_reference', None)
            values.pop('price_currency_id', None)
            values.pop('pricing_warning', None)
            values.pop('pricing_eligible', None)
            values.pop('pricing_reprice_pending', None)
            prepared_vals.append(values)
            pricing_defaults.append((
                factor,
                protected_order.currency_id.id,
                incoming_price,
                bool(protected_order.product_pricing),
            ))
        lines = super(
            SaleOrderLine,
            self.with_context(_pricing_internal_token=_PRICING_INTERNAL_TOKEN),
        ).create(prepared_vals)
        for line, (factor, currency_id, incoming_price, product_pricing) in zip(
                lines, pricing_defaults):
            if line.display_type or (line.is_downpayment and _is_pricing_downpayment(self.env)):
                continue
            protected_line = line.sudo()
            pricelist_price = line._pricing_pricelist_price() if line.product_id else 0.0
            currency = line.order_id.currency_id
            manual_price = (
                incoming_price is not None
                and float_compare(
                    incoming_price,
                    pricelist_price,
                    precision_rounding=currency.rounding,
                ) != 0
            )
            # The web client includes a canonical price_unit in create
            # commands even when the user did not deliberately edit it. A
            # non-price-editor cannot turn that payload into a manual price;
            # safely normalize it back to the pricelist instead of rejecting
            # the whole one2many save.
            manual_price = (
                manual_price and line._pricing_manual_price_authorized()
            )

            if manual_price:
                selling_price = incoming_price
                origin = 'edited'
                evidence = 'manual_edit'
                warning = False
                reason = _('New quotation line keeps the authorized manual selling price.')
            elif product_pricing and protected_line.purchase_price_estimate > 0:
                selling_price = (
                    protected_line.purchase_price_estimate
                    * (factor or 1.0)
                    * (protected_line.currency_rate_estimate or 1.0)
                    * (protected_line.line_factor or 1.0)
                )
                origin = 'product_pricing'
                evidence = 'product_pricing_apply'
                warning = False
                reason = _('New quotation line automatically uses the active Product Pricing formula.')
            else:
                selling_price = pricelist_price
                origin = 'pricelist'
                evidence = 'new_pricelist'
                warning = (
                    _('No purchasing cost: Product Pricing is ineligible; Odoo Price List is used.')
                    if not protected_line.purchase_price_estimate else False
                )
                reason = _('New quotation line uses Odoo Price List.')
            protected_line.with_context(_pricing_internal_token=_PRICING_INTERNAL_TOKEN).write({
                'factor': factor,
                'price_unit': selling_price,
                'price_reference': selling_price if origin != 'edited' else pricelist_price,
                'price_origin': origin,
                'price_origin_verified': True,
                'price_origin_evidence': evidence,
                'price_currency_id': currency_id,
                'pricing_warning': warning,
                'pricing_reprice_pending': False,
            })
            line.order_id._pricing_log_line(
                line, reason,
                old_price=0.0, old_origin=False)
        # Do not return a recordset carrying the internal bypass token. Validate
        # the fully initialized values using the same rules as public writes.
        public_lines = lines.with_context(_pricing_internal_token=None)
        public_lines._check_purchase_price_estimate()
        return public_lines

    @api.depends(
        'product_id', 'product_uom', 'product_uom_qty',
        'order_id.pricelist_id', 'order_id.partner_id', 'order_id.date_order',
        'order_id.currency_id',
    )
    def _compute_price_unit(self):
        """Keep protected quoted prices stable during browser onchange.

        Odoo recomputes price_unit for quantity, UoM, customer and date
        changes. That is appropriate only for a verified Odoo Pricelist line.
        Product Pricing, Manual Price, and unverified historical values remain
        visible until an explicit controlled reprice.
        """
        protected_prices = {}
        for line in self:
            persisted = line._origin
            if not persisted or not persisted.id:
                continue
            protected_line = persisted.sudo()
            if not (
                protected_line.price_origin == 'pricelist'
                and protected_line.price_origin_verified
            ):
                protected_prices[line.id] = line.price_unit

        super()._compute_price_unit()

        for line in self:
            if line.id in protected_prices:
                line.price_unit = protected_prices[line.id]
            elif (
                (not line._origin or not line._origin.id)
                and line.order_id.product_pricing
                and line.purchase_price_estimate > 0
            ):
                # The web client has not created this row yet.  Keep every new
                # row, including the final row, aligned with the already active
                # Product Pricing formula without requiring another Apply.
                line.factor = line.order_id.global_factor or 1.0
                line.price_unit = line._pricing_target_price()

    def write(self, vals):
        if _is_pricing_internal(self.env):
            return super().write(vals)

        vals = dict(vals)
        if vals.get('is_downpayment') and not _is_pricing_downpayment(self.env):
            raise UserError(_('The down-payment marker is managed by the standard invoice wizard.'))
        # Origins and baselines are system-managed. A direct selling-price write
        # is tracked below as Edited, while a direct metadata write cannot forge
        # a pricing source or erase the audit baseline.
        vals.pop('price_origin', None)
        vals.pop('price_origin_verified', None)
        vals.pop('price_origin_evidence', None)
        vals.pop('price_reference', None)
        vals.pop('price_currency_id', None)
        vals.pop('pricing_warning', None)
        vals.pop('pricing_reprice_pending', None)
        if not vals:
            return True
        if vals.get('purchase_price_estimate', 0) < 0:
            raise ValidationError(_('Purchasing cost cannot be negative.'))
        pricing_input_change = bool(
            {'product_id', 'product_uom', 'product_uom_qty'} & set(vals)
        )
        cost_change = 'purchase_price_estimate' in vals
        price_change = 'price_unit' in vals
        if price_change and not pricing_input_change and not self._pricing_manual_price_authorized():
            raise UserError(_(
                'Only Product Pricing users or Sales Managers may manually edit a selling price.'))
        previous_costs = {line.id: line.sudo().purchase_price_estimate for line in self}
        previous_prices = {line.id: line.price_unit for line in self}
        previous_origins = {line.id: line.sudo().price_origin for line in self}
        previous_products = {line.id: line.product_id.display_name for line in self}
        previous_uoms = {line.id: line.product_uom.display_name for line in self}
        previous_quantities = {line.id: line.product_uom_qty for line in self}

        # Customer/date onchange saves can include browser-generated price_unit
        # values. These are automatic recomputations, not manual price edits.
        if (_is_pricing_order_recompute(self.env)
                and price_change and not pricing_input_change):
            for line in self:
                protected_line = line.sudo()
                old_price = previous_prices[line.id]
                old_origin = previous_origins[line.id]
                line_vals = dict(vals)
                can_reprice = (
                    protected_line.price_origin == 'pricelist'
                    and protected_line.price_origin_verified
                )
                if can_reprice:
                    line_vals.pop('price_unit', None)
                    super(SaleOrderLine, line).write(line_vals)
                    pricelist_price = line._pricing_pricelist_price()
                    protected_line.with_context(
                        _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
                    ).write({
                        'price_unit': pricelist_price,
                        'price_reference': pricelist_price,
                        'price_origin': 'pricelist',
                        'price_origin_verified': True,
                        'price_origin_evidence': 'new_pricelist',
                        'price_currency_id': line.order_id.currency_id.id,
                        'pricing_reprice_pending': False,
                    })
                    line.order_id._pricing_log_line(
                        line,
                        _('Verified Odoo Pricelist refreshed after customer/date change.'),
                        old_price=old_price,
                        old_origin=old_origin,
                    )
                else:
                    line_vals['price_unit'] = old_price
                    super(SaleOrderLine, line).write(line_vals)
            return True

        # An existing product/UoM replacement never silently accepts the client
        # onchange price. It is held at the current selling price until preview.
        if pricing_input_change:
            for line in self:
                line_vals = dict(vals)
                line_vals.pop('price_origin', None)
                line_vals.pop('price_origin_verified', None)
                line_vals.pop('price_origin_evidence', None)
                line_vals.pop('price_reference', None)
                line_vals.pop('price_currency_id', None)
                protected_line = line.sudo()
                can_reprice_pricelist = (
                    'product_id' not in vals
                    and protected_line.price_origin == 'pricelist'
                    and protected_line.price_origin_verified
                    and not cost_change
                )
                if can_reprice_pricelist:
                    # First persist quantity/UoM without trusting the browser
                    # price, then compare that payload to the authoritative
                    # pricelist result. Matching input is an automatic onchange;
                    # a different authorized value is a deliberate manual edit.
                    line_vals.pop('price_unit', None)
                    super(SaleOrderLine, line).write(line_vals)
                    pricelist_price = line._pricing_pricelist_price()
                    explicit_manual_price = (
                        price_change
                        and line._pricing_manual_price_authorized()
                        and float_compare(
                            vals['price_unit'],
                            pricelist_price,
                            precision_rounding=line.order_id.currency_id.rounding,
                        ) != 0
                    )
                    if explicit_manual_price:
                        protected_line.with_context(
                            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
                        ).write({
                            'price_unit': vals['price_unit'],
                            'price_reference': pricelist_price,
                            'price_origin': 'edited',
                            'price_origin_verified': True,
                            'price_origin_evidence': 'manual_edit',
                            'price_currency_id': line.order_id.currency_id.id,
                            'pricing_reprice_pending': False,
                            'pricing_warning': False,
                        })
                        line.order_id._pricing_log_line(
                            line,
                            _('Authorized manual selling-price edit saved with quantity or UoM changes.'),
                            old_price=previous_prices[line.id],
                            old_origin=previous_origins[line.id],
                        )
                    else:
                        protected_line.with_context(
                            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
                        ).write({
                            'price_unit': pricelist_price,
                            'price_reference': pricelist_price,
                            'price_origin': 'pricelist',
                            'price_origin_verified': True,
                            'price_origin_evidence': 'new_pricelist',
                            'price_currency_id': line.order_id.currency_id.id,
                            'pricing_reprice_pending': False,
                        })
                        line.order_id._pricing_log_line(
                            line,
                            _('Verified Odoo Pricelist refreshed after quantity or UoM change.'),
                            old_price=previous_prices[line.id],
                            old_origin=previous_origins[line.id],
                        )
                    continue
                explicit_manual_price = (
                    price_change
                    and line._pricing_manual_price_authorized()
                    and float_compare(
                        vals['price_unit'],
                        previous_prices[line.id],
                        precision_rounding=line.order_id.currency_id.rounding,
                    ) != 0
                )
                if explicit_manual_price:
                    super(SaleOrderLine, line).write(line_vals)
                    protected_line.with_context(
                        _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
                    ).write({
                        'price_reference': line._pricing_pricelist_price(),
                        'price_origin': 'edited',
                        'price_origin_verified': True,
                        'price_origin_evidence': 'manual_edit',
                        'price_currency_id': line.order_id.currency_id.id,
                        'pricing_reprice_pending': False,
                        'pricing_warning': False,
                    })
                    line.order_id._pricing_log_line(
                        line,
                        _('Authorized manual selling-price edit saved with product, UoM, or quantity changes.'),
                        old_price=previous_prices[line.id],
                        old_origin=previous_origins[line.id],
                    )
                    continue
                # Odoo's standard product/UoM onchange may include or derive a
                # fresh pricelist price even when the client did not explicitly
                # send ``price_unit``.  Hold the existing selling price until
                # the controlled preview/apply workflow approves a reprice.
                line_vals['price_unit'] = line.price_unit
                super(SaleOrderLine, line).write(line_vals)
                if not line.display_type and not line.is_downpayment:
                    protected_line = line.sudo()
                    reference = line._pricing_pricelist_price()
                    if (cost_change and previous_costs[line.id] > 0
                            and not protected_line.purchase_price_estimate):
                        protected_line.with_context(
                            _pricing_internal_token=_PRICING_INTERNAL_TOKEN
                        ).write({
                            'price_unit': reference,
                            'price_reference': reference,
                            'price_origin': 'pricelist',
                            'price_origin_verified': True,
                            'price_origin_evidence': 'new_pricelist',
                            'price_currency_id': line.order_id.currency_id.id,
                            'pricing_warning': _(
                                'Purchasing cost changed to zero; Odoo Price List is used.'),
                            'pricing_reprice_pending': False,
                        })
                        line.order_id._pricing_log_line(
                            line, _('Purchasing cost changed to zero; Odoo Price List is now required.'),
                            old_price=previous_prices[line.id], old_origin=previous_origins[line.id])
                    else:
                        protected_line.with_context(
                            _pricing_internal_token=_PRICING_INTERNAL_TOKEN
                        ).write({
                            'price_reference': reference,
                            'pricing_reprice_pending': True,
                            'pricing_warning': (
                                False if protected_line.purchase_price_estimate else _(
                                    'No purchasing cost: replacement will use Odoo Price List on Apply.')),
                        })
                        line.order_id._pricing_log_line(
                            line, _('Product, UoM, or quantity changed from %(old_product)s / %(old_uom)s / '
                                    '%(old_qty)s; selling price is unchanged until '
                                    'Product Pricing is previewed and applied.') % {
                                'old_product': previous_products[line.id],
                                'old_uom': previous_uoms[line.id],
                                'old_qty': previous_quantities[line.id],
                            }, old_price=previous_prices[line.id], old_origin=previous_origins[line.id])
            return True

        result = super().write(vals)
        if price_change:
            # Core ACL and record rules have already authorized this write.  Any
            # non-automatic selling-price edit is explicitly protected from Apply.
            self.sudo().with_context(_pricing_internal_token=_PRICING_INTERNAL_TOKEN).write({
                'price_origin': 'edited',
                'price_origin_verified': True,
                'price_origin_evidence': 'manual_edit',
                'pricing_reprice_pending': False,
            })
            for line in self:
                line.sudo().with_context(_pricing_internal_token=_PRICING_INTERNAL_TOKEN).write({
                    'price_currency_id': line.order_id.currency_id.id,
                })
                line.order_id._pricing_log_line(
                    line, _('Authorized manual selling-price edit.'),
                    old_price=previous_prices[line.id], old_origin=previous_origins[line.id])
        if cost_change:
            for line in self:
                protected_line = line.sudo()
                if previous_costs[line.id] > 0 and not protected_line.purchase_price_estimate:
                    pricelist_price = line._pricing_pricelist_price()
                    protected_line.with_context(
                        _pricing_internal_token=_PRICING_INTERNAL_TOKEN
                    ).write({
                        'price_unit': pricelist_price,
                        'price_reference': pricelist_price,
                        'price_origin': 'pricelist',
                        'price_origin_verified': True,
                        'price_origin_evidence': 'new_pricelist',
                        'price_currency_id': line.order_id.currency_id.id,
                        'pricing_warning': _(
                            'Purchasing cost changed to zero; Odoo Price List is used.'),
                        'pricing_reprice_pending': False,
                    })
                    line.order_id._pricing_log_line(
                        line, _('Purchasing cost changed to zero; Odoo Price List is now required.'),
                        old_price=previous_prices[line.id], old_origin=previous_origins[line.id])
                elif previous_costs[line.id] <= 0 < protected_line.purchase_price_estimate:
                    protected_line.with_context(
                        _pricing_internal_token=_PRICING_INTERNAL_TOKEN
                    ).write({
                        'pricing_warning': False,
                    })
        return result

    @api.depends('purchase_price_estimate')
    def _compute_pricing_eligible(self):
        for line in self:
            line.pricing_eligible = line.purchase_price_estimate > 0

    @api.constrains('purchase_price_estimate', 'factor', 'line_factor', 'currency_rate_estimate')
    def _check_purchase_price_estimate(self):
        if _is_pricing_internal(self.env):
            return
        protected_lines = self.sudo()
        if any(line.purchase_price_estimate < 0 for line in protected_lines):
            raise ValidationError(_('Purchasing cost cannot be negative.'))
        if any(
                line.purchase_price_estimate > 0
                and (line.factor <= 0 or line.line_factor <= 0 or line.currency_rate_estimate <= 0)
                for line in protected_lines):
            raise ValidationError(_('Factor, line factor, and currency rate must all be positive.'))

    @api.onchange('order_id')
    def _onchange_order_id_pricing_factor(self):
        for line in self:
            if line.order_id and not line.factor:
                line.factor = line.order_id.sudo().global_factor

    @api.onchange('purchase_price_estimate', 'factor', 'line_factor')
    def _onchange_new_line_product_pricing(self):
        """Price an unsaved eligible row immediately from the active formula."""
        for line in self:
            if (
                (not line._origin or not line._origin.id)
                and line.order_id.product_pricing
                and line.purchase_price_estimate > 0
            ):
                line.factor = line.order_id.global_factor or 1.0
                line.price_unit = line._pricing_target_price()

    @api.onchange('product_uom_qty')
    def _onchange_product_uom_qty_estimate(self):
        for line in self:
            line.qty_estimate = line.product_uom_qty

    @api.depends('factor', 'purchase_price_estimate', 'currency_rate_estimate', 'line_factor')
    def _compute_estimate_unit_price(self):
        for line in self:
            line.estimate_unit_price = line._pricing_target_price()

    @api.depends('order_id.currency_estimate_id')
    def _compute_currency_estimate(self):
        for line in self:
            line.currency_estimate_id = line.order_id.currency_estimate_id

    @api.depends('order_id.currency_rate_inverse', 'order_id.change_currency_rate_type',
                 'order_id.change_currency_rate', 'order_id.currency_estimate_id', 'order_id.currency_id')
    def _compute_currency_rate_estimate(self):
        for line in self:
            order = line.order_id
            rate = order.currency_rate_inverse or 1.0
            if not order.currency_estimate_id or order.currency_estimate_id == order.currency_id:
                rate = 1.0
            elif order.change_currency_rate_type == 'percentage':
                rate += rate * (order.change_currency_rate / 100.0)
            elif order.change_currency_rate_type == 'amount':
                rate += order.change_currency_rate
            line.currency_rate_estimate = rate

    def _pricing_target_price(self):
        self.ensure_one()
        factor = self.factor or 1.0
        return self.purchase_price_estimate * factor * (self.currency_rate_estimate or 1.0) * (self.line_factor or 1.0)

    def _pricing_pricelist_price(self):
        self.ensure_one()
        if not self.product_id or not self.order_id.pricelist_id:
            return self.price_unit
        return self._get_display_price()

    def _pricing_convert_price(self, amount, from_currency, to_currency):
        self.ensure_one()
        if not from_currency or not to_currency or from_currency == to_currency:
            return amount
        date = fields.Date.to_date(self.order_id.date_order) or fields.Date.context_today(self)
        return from_currency._convert(amount, to_currency, self.order_id.company_id, date)

    def _pricing_manual_price_authorized(self):
        user = self.env.user
        return self.env.is_superuser() or user.has_group(
            'sale_order_product_pricing.product_pricing_group') or user.has_group(
            'sales_team.group_sale_manager')

    def action_reclassify_historical_origin(self):
        self.ensure_one()
        user = self.env.user
        if not self.env.is_superuser() and not user.has_group('sales_team.group_sale_manager'):
            raise UserError(_('Only a Sales Manager may certify a historical Price Origin.'))
        if self.price_origin != 'historical_unverified' or self.price_origin_verified:
            raise UserError(_('This line no longer requires historical origin review.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reclassify Historical Price Origin'),
            'res_model': 'sale.order.price.origin.reclassify',
            'view_mode': 'form',
            'view_id': self.env.ref(
                'sale_order_product_pricing.sale_order_price_origin_reclassify_form'
            ).id,
            'target': 'new',
            'context': {'default_line_id': self.id},
        }

class SaleOrderPricingAudit(models.Model):
    _name = 'sale.order.pricing.audit'
    _description = 'Quotation Pricing Audit'
    _order = 'event_date desc, id desc'
    _check_company_auto = True

    order_id = fields.Many2one(
        'sale.order', required=True, ondelete='cascade', index=True,
        check_company=True, readonly=True)
    line_id = fields.Many2one(
        'sale.order.line', ondelete='set null', index=True, readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    company_id = fields.Many2one(
        related='order_id.company_id', store=True, index=True, readonly=True)
    old_price = fields.Monetary(currency_field='old_currency_id', readonly=True)
    new_price = fields.Monetary(currency_field='new_currency_id', readonly=True)
    old_currency_id = fields.Many2one('res.currency', readonly=True)
    new_currency_id = fields.Many2one('res.currency', readonly=True)
    old_origin = fields.Selection(
        [('product_pricing', 'Product Pricing'),
         ('pricelist', 'Odoo Pricelist'),
         ('edited', 'Manual Price'),
         ('historical_unverified', 'Historical—Unverified')],
        readonly=True)
    new_origin = fields.Selection(
        [('product_pricing', 'Product Pricing'),
         ('pricelist', 'Odoo Pricelist'),
         ('edited', 'Manual Price'),
         ('historical_unverified', 'Historical—Unverified')],
        readonly=True)
    reason = fields.Text(required=True, readonly=True)
    user_id = fields.Many2one('res.users', required=True, readonly=True)
    event_date = fields.Datetime(
        default=fields.Datetime.now, required=True, readonly=True)


class SaleOrderPriceOriginReclassify(models.TransientModel):
    _name = 'sale.order.price.origin.reclassify'
    _description = 'Historical Price Origin Reclassification'

    line_id = fields.Many2one(
        'sale.order.line', string='Quotation Line', required=True, readonly=True)
    current_origin = fields.Char(
        string='Current Origin', related='line_id.price_origin_label', readonly=True)
    new_origin = fields.Selection(
        [('product_pricing', 'Product Pricing'),
         ('pricelist', 'Odoo Pricelist'),
         ('edited', 'Manual Price')],
        string='Certified Origin', required=True,
        help='Select the price source supported by the recorded evidence.')
    reason = fields.Text(
        string='Evidence and Reason', required=True,
        help='State the document, calculation, or business evidence used to certify this historical price.')

    def action_confirm(self):
        self.ensure_one()
        user = self.env.user
        if not self.env.is_superuser() and not user.has_group('sales_team.group_sale_manager'):
            raise UserError(_('Only a Sales Manager may certify a historical Price Origin.'))
        line = self.line_id
        if not line.exists() or line.price_origin != 'historical_unverified' or line.price_origin_verified:
            raise UserError(_('This historical line changed while the dialog was open. Reopen it and try again.'))
        reason = (self.reason or '').strip()
        if not reason:
            raise UserError(_('Evidence and Reason are required.'))
        order = line.order_id
        old_price = line.price_unit
        old_origin = line.price_origin
        line.sudo().with_context(
            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
            _pricing_reclassify_token=_PRICING_RECLASSIFY_TOKEN,
        ).write({
            'price_origin': self.new_origin,
            'price_origin_verified': True,
            'price_origin_evidence': 'manager_reclassified',
            'pricing_warning': False,
        })
        order._pricing_log_line(
            line,
            _('Historical Price Origin certified by Sales Manager. Evidence: %s') % reason,
            old_price=old_price,
            old_origin=old_origin,
        )
        return {'type': 'ir.actions.act_window_close'}
class SaleOrderPricingPreview(models.TransientModel):
    _name = 'sale.order.pricing.preview'
    _description = 'Product Pricing Preview'

    order_id = fields.Many2one('sale.order', required=True, readonly=True)
    preview_hash = fields.Char(required=True, readonly=True)
    line_ids = fields.One2many(
        'sale.order.pricing.preview.line', 'wizard_id', readonly=True)
    ready_count = fields.Integer(readonly=True)
    protected_count = fields.Integer(readonly=True)
    skipped_count = fields.Integer(readonly=True)
    blocked_count = fields.Integer(readonly=True)
    can_apply = fields.Boolean(readonly=True)

    def action_confirm_apply(self):
        self.ensure_one()
        if not self.can_apply:
            raise UserError(_(
                'Resolve every blocked Product Pricing line and preview again before Apply.'
            ))
        current_preview = self.order_id._pricing_preview_payload()
        if self.preview_hash != self.order_id._pricing_preview_hash(current_preview):
            raise UserError(_(
                'Pricing inputs changed after this dialog opened. Close it and preview again.'
            ))
        self.order_id.with_context(
            pricing_apply_confirmed=True
        ).action_apply_product_pricing()
        return {'type': 'ir.actions.act_window_close'}


class SaleOrderPricingPreviewLine(models.TransientModel):
    _name = 'sale.order.pricing.preview.line'
    _description = 'Product Pricing Preview Line'
    _order = 'id'

    wizard_id = fields.Many2one(
        'sale.order.pricing.preview', required=True, ondelete='cascade', readonly=True)
    sale_line_id = fields.Many2one('sale.order.line', required=True, readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    product_uom_id = fields.Many2one('uom.uom', readonly=True)
    quantity = fields.Float(readonly=True)
    purchase_cost = fields.Monetary(
        currency_field='cost_currency_id', readonly=True)
    cost_currency_id = fields.Many2one('res.currency', readonly=True)
    factor = fields.Float(readonly=True)
    line_factor = fields.Float(readonly=True)
    currency_rate = fields.Float(readonly=True)
    status = fields.Selection(
        [('ready', 'Ready'), ('protected', 'Edited - Protected'),
         ('skipped', 'Skipped'), ('blocked', 'Blocked')],
        required=True, readonly=True)
    origin = fields.Selection(
        [('product_pricing', 'Product Pricing'),
         ('pricelist', 'Odoo Pricelist'),
         ('edited', 'Manual Price'),
         ('historical_unverified', 'Historical—Unverified')],
        required=True, readonly=True)
    current_price = fields.Monetary(
        currency_field='current_currency_id', readonly=True)
    proposed_price = fields.Monetary(
        currency_field='proposed_currency_id', readonly=True)
    current_currency_id = fields.Many2one('res.currency', readonly=True)
    proposed_currency_id = fields.Many2one('res.currency', readonly=True)
    reason = fields.Text(readonly=True)
    conversion_required = fields.Boolean(readonly=True)
    reprice_required = fields.Boolean(readonly=True)


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def _create_invoices(self, sale_orders):
        """Authorize only the standard wizard's genuine down-payment line create."""
        return super(SaleAdvancePaymentInv, self.with_context(
            _pricing_downpayment_token=_PRICING_DOWNPAYMENT_TOKEN
        ))._create_invoices(sale_orders)
