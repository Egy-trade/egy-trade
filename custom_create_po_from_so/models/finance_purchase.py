# -*- coding: utf-8 -*-
"""Quotation-estimate provenance and supplier-cost controls on generated RFQs."""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare


_SUPPLIER_COST_INTERNAL_TOKEN = object()
_PURCHASE_PROVENANCE_TOKEN = object()


def _is_supplier_cost_internal(env):
    return env.context.get('_supplier_cost_internal_token') is _SUPPLIER_COST_INTERNAL_TOKEN


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _estimate_price_in_purchase_currency(self, purchase_order):
        """Use the quotation's saved estimate/rate, never a later product cost."""
        self.ensure_one()
        estimate_currency = self.order_id.currency_estimate_id or self.order_id.currency_id
        if estimate_currency == purchase_order.currency_id:
            return self.purchase_price_estimate
        # ``currency_rate_inverse`` is the stored estimate-to-quotation
        # conversion captured during pricing.  ``currency_rate_estimate`` is
        # the opposite company-to-estimate rate and must never seed an RFQ.
        if purchase_order.currency_id == self.order_id.currency_id:
            return self.purchase_price_estimate * self.order_id.currency_rate_inverse
        date = fields.Date.to_date(self.order_id.date_order) or fields.Date.context_today(self)
        return estimate_currency._convert(
            self.purchase_price_estimate, purchase_order.currency_id,
            purchase_order.company_id, date,
        )

    def _purchase_service_prepare_line_values(self, purchase_order, quantity=False):
        values = super()._purchase_service_prepare_line_values(purchase_order, quantity=quantity)
        self.ensure_one()
        estimate = self.purchase_price_estimate
        values.update({
            'source_sale_order_id': self.order_id.id,
            'source_sale_line_id': self.id,
            'purchase_estimate_amount': estimate,
            'purchase_estimate_currency_id': self.order_id.currency_estimate_id.id,
            'purchase_estimate_rate': self.order_id.currency_rate_inverse,
            '_finance_purchase_provenance_token': _PURCHASE_PROVENANCE_TOKEN,
        })
        if estimate > 0.0:
            values['price_unit'] = self._estimate_price_in_purchase_currency(purchase_order)
            values['supplier_cost_required'] = False
        elif float_compare(values.get('price_unit', 0.0), 0.0,
                           precision_rounding=purchase_order.currency_id.rounding) == 0:
            values['supplier_cost_required'] = True
        return values

    def _prepare_procurement_values(self, group_id=False):
        values = super()._prepare_procurement_values(group_id=group_id)
        values['sale_line_id'] = self.id
        values['_finance_purchase_provenance_token'] = _PURCHASE_PROVENANCE_TOKEN
        return values


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_confirm(self):
        for order in self:
            unresolved = order.order_line.filtered(
                lambda line: line.supplier_cost_required or (
                    line.source_sale_line_id and not line.purchase_estimate_amount and
                    float_compare(line.price_unit, 0.0, precision_rounding=order.currency_id.rounding) <= 0
                )
            )
            if unresolved:
                raise UserError(_(
                    'Purchase Order confirmation is blocked: Procurement must enter the actual supplier cost and reason for every Supplier Cost Required line.'
                ))
        return super().button_confirm()


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    source_sale_order_id = fields.Many2one(
        'sale.order', string='Source Quotation', readonly=True, copy=False,
        help='System-recorded quotation that generated this RFQ line; Procurement cannot edit it.',
    )
    source_sale_line_id = fields.Many2one(
        'sale.order.line', string='Source Quotation Line', readonly=True, copy=False,
        help='System-recorded quotation line used for estimate provenance; Procurement cannot edit it.',
    )
    purchase_estimate_amount = fields.Monetary(string='Purchase Price Estimate', readonly=True, copy=False,
                                                currency_field='purchase_estimate_currency_id',
                                                help='Read-only quotation estimate used to seed this draft RFQ line when non-zero.')
    purchase_estimate_currency_id = fields.Many2one(
        'res.currency', string='Estimate Currency', readonly=True, copy=False,
        help='Currency saved with the quotation estimate when this draft RFQ was generated.',
    )
    purchase_estimate_rate = fields.Float(
        string='Stored Estimate Rate', readonly=True, copy=False, digits=(12, 6),
        help='Quotation conversion rate retained as evidence for the initial RFQ price.',
    )
    supplier_cost_required = fields.Boolean(string='Supplier Cost Required', readonly=True, copy=False,
                                            help='The quotation had no estimate and no valid vendor price. Procurement must record the actual cost and reason before confirmation.')
    supplier_cost_reason = fields.Text(
        string='Actual Supplier Cost Reason', copy=False,
        help='Procurement states the vendor evidence or reason when replacing a required zero supplier cost.',
    )
    supplier_cost_recorded_by = fields.Many2one('res.users', readonly=True, copy=False)
    supplier_cost_recorded_at = fields.Datetime(readonly=True, copy=False)

    @classmethod
    def _purchase_estimate_values(cls, sale_line, purchase_order, values):
        """Decorate both service and MTO RFQ values with immutable estimate evidence."""
        estimate = sale_line.purchase_price_estimate
        values.update({
            'source_sale_order_id': sale_line.order_id.id,
            'source_sale_line_id': sale_line.id,
            'purchase_estimate_amount': estimate,
            'purchase_estimate_currency_id': sale_line.order_id.currency_estimate_id.id,
            'purchase_estimate_rate': sale_line.order_id.currency_rate_inverse,
            '_finance_purchase_provenance_token': _PURCHASE_PROVENANCE_TOKEN,
        })
        if estimate > 0.0:
            values['price_unit'] = sale_line._estimate_price_in_purchase_currency(purchase_order)
            values['supplier_cost_required'] = False
        elif float_compare(values.get('price_unit', 0.0), 0.0,
                           precision_rounding=purchase_order.currency_id.rounding) == 0:
            values['supplier_cost_required'] = True
        return values

    @classmethod
    def _purchase_line_from_values(cls, env, values):
        sale_line = values.get('sale_line_id')
        if isinstance(sale_line, int):
            sale_line = env['sale.order.line'].browse(sale_line)
        return sale_line if sale_line and sale_line.exists() else env['sale.order.line']

    @classmethod
    def _decorate_procurement_purchase_values(cls, env, values, purchase_order, line_values):
        sale_line = cls._purchase_line_from_values(env, values)
        return cls._purchase_estimate_values(sale_line, purchase_order, line_values) if sale_line else line_values

    @api.model
    def _prepare_purchase_order_line_from_procurement(self, product_id, product_qty, product_uom,
                                                       company, values, purchase_order):
        line_values = super()._prepare_purchase_order_line_from_procurement(
            product_id, product_qty, product_uom, company, values, purchase_order
        )
        return self._decorate_procurement_purchase_values(self.env, values, purchase_order, line_values)

    def _find_candidate(self, product_id, product_qty, product_uom, location_id, name, origin,
                        company_id, values):
        """Keep MTO quotation evidence one source line per generated RFQ line.

        The stock purchase flow normally merges matching product lines.  A
        second quotation line must not replace the first line's immutable
        estimate/provenance fields, so only a repeat procurement for the same
        sale line is eligible for that merge.
        """
        sale_line = self._purchase_line_from_values(self.env, values)
        if not sale_line:
            return super()._find_candidate(
                product_id, product_qty, product_uom, location_id, name, origin,
                company_id, values,
            )
        candidates = self.filtered(lambda line: line.source_sale_line_id == sale_line)
        return super(PurchaseOrderLine, candidates)._find_candidate(
            product_id, product_qty, product_uom, location_id, name, origin,
            company_id, values,
        )
    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for incoming in vals_list:
            vals = dict(incoming)
            provenance_token = vals.pop('_finance_purchase_provenance_token', None)
            provenance_fields = {
                'source_sale_order_id', 'source_sale_line_id',
                'purchase_estimate_amount', 'purchase_estimate_currency_id',
                'purchase_estimate_rate',
            }
            audit_fields = {
                'supplier_cost_required', 'supplier_cost_recorded_by',
                'supplier_cost_recorded_at',
            }
            if provenance_fields.intersection(vals) and provenance_token is not _PURCHASE_PROVENANCE_TOKEN:
                raise AccessError(_('Quotation purchase-estimate provenance is system-managed and cannot be supplied through RPC/import.'))
            if (audit_fields.intersection(vals) and
                    provenance_token is not _PURCHASE_PROVENANCE_TOKEN and
                    not _is_supplier_cost_internal(self.env)):
                raise AccessError(_('Supplier Cost Required audit fields are system-managed and cannot be supplied through RPC/import.'))
            sale_line = self._purchase_line_from_values(self.env, vals)
            if provenance_token is _PURCHASE_PROVENANCE_TOKEN and sale_line:
                purchase_order = self.env['purchase.order'].browse(vals.get('order_id'))
                vals = self._purchase_estimate_values(sale_line, purchase_order, vals)
                vals.pop('_finance_purchase_provenance_token', None)
            if sale_line and not sale_line.purchase_price_estimate and float_compare(
                    vals.get('price_unit', 0.0), 0.0,
                    precision_rounding=self.env['res.currency'].browse(
                        vals.get('currency_id') or self.env.company.currency_id.id
                    ).rounding,
            ) <= 0:
                vals['supplier_cost_required'] = True
            prepared.append(vals)
        lines = super().create(prepared)
        # Keep the generated audit flag authoritative even if another
        # purchase-line create override normalizes readonly values.
        unresolved = lines.filtered(
            lambda line: line.source_sale_line_id
            and not line.purchase_estimate_amount
            and float_compare(
                line.price_unit, 0.0,
                precision_rounding=line.order_id.currency_id.rounding,
            ) <= 0
        )
        if unresolved:
            unresolved.with_context(
                _supplier_cost_internal_token=_SUPPLIER_COST_INTERNAL_TOKEN,
            ).write({'supplier_cost_required': True})
        return lines

    def write(self, vals):
        vals = dict(vals)
        protected = {'supplier_cost_required', 'supplier_cost_recorded_by', 'supplier_cost_recorded_at'}
        protected |= {
            'source_sale_order_id', 'source_sale_line_id',
            'purchase_estimate_amount', 'purchase_estimate_currency_id', 'purchase_estimate_rate',
        }
        if protected.intersection(vals) and not _is_supplier_cost_internal(self.env):
            raise AccessError(_('Supplier Cost Required audit fields are system-managed.'))
        if _is_supplier_cost_internal(self.env) or 'price_unit' not in vals:
            return super().write(vals)
        # Apply each transition separately: an RPC multi-write must not clear a
        # second line merely because the first line supplied its actual cost.
        for line in self:
            new_price = vals['price_unit']
            if line.supplier_cost_required and new_price > 0.0:
                reason = vals.get('supplier_cost_reason', line.supplier_cost_reason)
                if not (reason or '').strip():
                    raise ValidationError(_('Procurement must state why this actual supplier cost was selected.'))
                line.with_context(_supplier_cost_internal_token=_SUPPLIER_COST_INTERNAL_TOKEN).write(dict(vals, **{
                    'supplier_cost_required': False,
                    'supplier_cost_recorded_by': self.env.user.id,
                    'supplier_cost_recorded_at': fields.Datetime.now(),
                }))
                line.order_id.message_post(body=_(
                    'Actual supplier cost recorded for %(product)s by %(user)s: %(reason)s'
                ) % {
                    'product': line.product_id.display_name,
                    'user': self.env.user.display_name,
                    'reason': reason,
                })
            else:
                super(PurchaseOrderLine, line).write(vals)
        return True


class StockRule(models.Model):
    _inherit = 'stock.rule'

    @api.model
    def _get_procurements_to_merge_groupby(self, procurement):
        """Never batch-merge procurement requests from different quotations."""
        source_sale_line = PurchaseOrderLine._purchase_line_from_values(
            self.env, procurement.values,
        )
        return (*super()._get_procurements_to_merge_groupby(procurement),
                source_sale_line.id or False)

    @api.model
    def _update_purchase_order_line(self, product_id, product_qty, product_uom, company_id,
                                    values, line):
        """Keep a repeated MTO procurement on its quotation estimate.

        Standard Odoo refreshes the supplier price while increasing a matched
        draft RFQ line.  For a line tied to the same quotation source, retain
        the captured estimate; for a zero estimate awaiting Procurement, do
        not let that background update clear the mandatory-cost workflow.
        """
        result = super()._update_purchase_order_line(
            product_id, product_qty, product_uom, company_id, values, line,
        )
        sale_line = PurchaseOrderLine._purchase_line_from_values(self.env, values)
        if sale_line and line.source_sale_line_id == sale_line:
            if sale_line.purchase_price_estimate > 0.0:
                result['price_unit'] = sale_line._estimate_price_in_purchase_currency(line.order_id)
            elif line.supplier_cost_required:
                result['price_unit'] = line.price_unit
        return result
