from odoo import models, fields, api
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    product_pricing = fields.Boolean(
        copy=True
    )
    total_estimate_unit_price = fields.Float(compute='_compute_estimate_unit_price')
    product_pricing_ids = fields.One2many('sale.order.line', 'order_id',
                                          copy=True,
                                          store=False, compute='change_order_line',
                                          readonly=False,precompute=True)
    currency_estimate_id = fields.Many2one('res.currency', string='Currency',
                                           copy=True,
                                           default=lambda self: self.env.company.currency_id)
    currency_estimate_id_symbol = fields.Char(related='currency_estimate_id.symbol')
    currency_rate_estimate = fields.Float(compute='_compute_currency_rate',digits=(12, 6),
                                          copy=True,
                                          store=True, precompute=True)
    currency_rate_inverse = fields.Float(compute='_compute_currency_rate_inverse')
    change_currency_rate_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], copy=True)
    change_currency_rate = fields.Float(copy=True)
    global_factor = fields.Float(copy=True)
    analysis_created = fields.Boolean(
        copy=False
    )

    @api.onchange('global_factor', 'order_line')
    def _onchange_global_factor(self):
        """ global_factor """
        for rec in self:
            if rec.product_pricing_ids:
                rec.product_pricing_ids.write({
                    'factor': rec.global_factor
                })

    def apply_estimate_product_price(self):
        for rec in self.order_line:
            if rec.estimate_unit_price:
                print(rec.estimate_unit_price)
                rec.product_uom_qty = rec.qty_estimate
                rec.price_unit = rec.estimate_unit_price

    # @api.depends('order_line')
    def change_order_line(self):
        self.product_pricing_ids = self.order_line

    @api.depends('product_pricing_ids.estimate_unit_price')
    def _compute_estimate_unit_price(self):
        for line in self:
            total = 0
            for rec in line.product_pricing_ids:
                total += rec.estimate_unit_price
            line.total_estimate_unit_price = total

    @api.onchange('change_currency_rate_type', 'change_currency_rate')
    @api.constrains('change_currency_rate')
    def check_currency_rate_type(self):
        if self.change_currency_rate_type == 'percentage' and self.change_currency_rate > 100:
            raise UserError('The change currency rate amount more then 100%')

    @api.onchange('change_currency_rate_type', 'change_currency_rate', 'currency_id','currency_estimate_id')
    def change_currency_rate_func(self):
        for rec in self.product_pricing_ids:
            if self.currency_estimate_id.rate == 1 or  rec.order_id.pricelist_id.currency_id == rec.order_id.currency_estimate_id:
                rec.currency_rate_estimate = 1
            else:
                if self.change_currency_rate_type == 'percentage':
                    rec.currency_rate_estimate = self.currency_rate_inverse + self.currency_rate_inverse * (
                            self.change_currency_rate / 100)
                elif self.change_currency_rate_type == 'amount':
                    rec.currency_rate_estimate = self.currency_rate_inverse + self.change_currency_rate
                else:
                    rec.currency_rate_estimate = self.currency_rate_inverse

    @api.depends('currency_id','currency_estimate_id')
    def _compute_currency_rate_inverse(self):
        for rec in self:
            rate = rec.currency_estimate_id.rate_ids.filtered(
                lambda l: l.name == max([x.name for x in rec.currency_estimate_id.rate_ids]))
            rec.currency_rate_inverse = rate.inverse_company_rate

    @api.constrains('state')
    def _check_state(self):
        """ Validate state """
        for rec in self:
            if rec.state == 'sent' and rec.order_line:
                lines = []
                for record in rec.order_line:
                    if record.estimate_unit_price:
                        lines += [{
                            'product_id': record.product_id.id,
                            'sale_id': record.order_id.id,
                            'quantity': record.product_uom_qty,
                            'purchase_price_estimate': record.purchase_price_estimate,
                            'factor': record.factor,
                            'currency_rate_estimate': record.currency_rate_estimate,
                            'note': record.note,
                        }]
                if lines:
                    self.env['product.analysis'].create(lines)
                    rec.analysis_created = True

    def action_quotation_send(self):
        """ Override action_quotation_send """
        lines = []
        for rec in self:
            if rec.order_line and not rec.analysis_created:
                for record in rec.order_line:
                    if record.estimate_unit_price:
                        lines += [{
                            'product_id': record.product_id.id,
                            'sale_id': record.order_id.id,
                            'quantity': record.product_uom_qty,
                            'purchase_price_estimate': record.purchase_price_estimate,
                            'factor': record.factor,
                            'currency_rate_estimate': record.currency_rate_estimate,
                            'note': record.note,
                        }]
                if lines:
                    self.env['product.analysis'].create(lines)
                    rec.analysis_created = True
        return super(SaleOrder, self).action_quotation_send()

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        lines = []
        for rec in self:
            if rec.order_line and not rec.analysis_created:
                for record in rec.order_line:
                    if record.estimate_unit_price:
                        lines += [{
                            'product_id': record.product_id.id,
                            'sale_id': record.order_id.id,
                            'quantity': record.product_uom_qty,
                            'purchase_price_estimate': record.purchase_price_estimate,
                            'factor': record.factor,
                            'currency_rate_estimate': record.currency_rate_estimate,
                            'note': record.note,
                        }]

        rec.env['product.analysis'].create(lines)

        return res

    @api.depends('currency_id', 'date_order', 'company_id','currency_estimate_id')
    def _compute_currency_rate(self):
        cache = {}
        for order in self:
            order_date = order.date_order.date()
            if not order.company_id:
                order.currency_rate = order.currency_id.with_context(date=order_date).rate or 1.0
                order.currency_rate_estimate = order.currency_estimate_id.with_context(date=order_date).rate or 1.0
                continue
            elif not order.currency_id:
                order.currency_rate = 1.0
                if not order.currency_estimate_id:
                    order.currency_rate_estimate = 1.0
            else:
                key = (order.company_id.id, order_date, order.currency_id.id)
                if key not in cache:
                    cache[key] = self.env['res.currency']._get_conversion_rate(
                        from_currency=order.company_id.currency_id,
                        to_currency=order.currency_id,
                        company=order.company_id,
                        date=order_date,
                    )
                order.currency_rate = cache[key]
                print(cache[key])
                key = (order.company_id.id, order_date, order.currency_estimate_id.id)
                if key not in cache:
                    print(key)
                    if order.currency_estimate_id:
                        cache[key] = self.env['res.currency']._get_conversion_rate(
                            from_currency=order.company_id.currency_id,
                            to_currency=order.currency_estimate_id,
                            company=order.company_id,
                            date=order_date,
                        )
                order.currency_rate_estimate = cache[key] if order.currency_estimate_id else False


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    purchase_price_estimate = fields.Float(copy=False)
    factor = fields.Float()
    line_factor = fields.Float(
        default=1
    )
    qty_estimate = fields.Float(string='Quantity', default=1)
    estimate_unit_price = fields.Float(compute='_compute_estimate_unit_price', store=True)
    currency_estimate_id = fields.Many2one('res.currency', string='Currency', compute='_compute_currency_estimate')

    currency_rate_estimate = fields.Float(compute='change_currency_rate_func', store=True)
    note = fields.Char(string='Note')

    @api.depends('factor', 'purchase_price_estimate', 'currency_id', 'product_uom_qty', 'currency_rate_estimate','currency_estimate_id', 'line_factor')
    def _compute_estimate_unit_price(self):
        for rec in self:
            rec.estimate_unit_price = rec.purchase_price_estimate * rec.factor * rec.currency_rate_estimate * rec.line_factor

    @api.depends('purchase_price_estimate', 'currency_id', 'product_uom_qty','currency_estimate_id')
    def _compute_currency_estimate(self):
        for rec in self:
            rec.currency_estimate_id = rec.order_id.currency_estimate_id
            # rec.currency_rate_estimate = rec.order_id.currency_rate_inverse

    @api.depends('purchase_price_estimate', 'currency_id', 'product_uom_qty', 'order_id.change_currency_rate_type',
                 'order_id.change_currency_rate','order_id.currency_estimate_id')
    def change_currency_rate_func(self):
        for rec in self:
            if rec.order_id.pricelist_id.currency_id == rec.order_id.currency_estimate_id:
                print('kkkkkkkk')
                rec.currency_rate_estimate = 1
                print(rec.currency_rate_estimate)
            else:
                print('nnnnnnnnnnn')
                if rec.order_id.currency_estimate_id.rate == 1:
                    print('jjjjjjjj')
                    rec.currency_rate_estimate = 1
                else:
                    if rec.order_id.change_currency_rate_type == 'percentage':
                        rec.currency_rate_estimate = rec.order_id.currency_rate_inverse + rec.order_id.currency_rate_inverse * (
                                rec.order_id.change_currency_rate / 100)
                    elif rec.order_id.change_currency_rate_type == 'amount':
                        rec.currency_rate_estimate = rec.order_id.currency_rate_inverse + rec.order_id.change_currency_rate

                    else:
                        rec.currency_rate_estimate = rec.order_id.currency_rate_inverse
                print(rec.currency_rate_estimate)

    @api.onchange('product_uom_qty')
    @api.constrains('product_uom_qty')
    def _onchange_product_uom_qty_estimate(self):
        """ product_uom_qty """
        for rec in self:
            rec.qty_estimate = rec.product_uom_qty