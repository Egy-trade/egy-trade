# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError
from odoo.tests.common import SavepointCase

from ..models.ks_account_invoice import _compound_discount as invoice_compound_discount
from ..models.ks_purchase_order import _compound_discount as purchase_compound_discount
from ..models.ks_sale_order import _compound_discount as sale_compound_discount


class TestUniversalDiscountStabilization(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref('base.res_partner_1')
        cls.product = cls.env['product.product'].create({
            'name': 'Universal discount regression product',
            'sale_ok': True,
            'list_price': 100.0,
        })

    def test_compound_discount_formula_is_consistent_across_models(self):
        for helper in (
                sale_compound_discount,
                purchase_compound_discount,
                invoice_compound_discount):
            self.assertAlmostEqual(helper(10.0, 20.0), 28.0)

    def test_sale_line_uses_compound_discount_without_nested_amount_writes(self):
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        line = self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product.id,
            'name': self.product.display_name,
            'product_uom': self.product.uom_id.id,
            'product_uom_qty': 2.0,
            'price_unit': 100.0,
            'discount_2': 10.0,
            'discount_3': 20.0,
        })

        self.assertAlmostEqual(line.discount, 28.0)
        self.assertAlmostEqual(line.price_subtotal, 144.0)
        self.assertAlmostEqual(line.tx_amount, line.price_tax)

    def test_fixed_amount_onchange_with_zero_base_returns_warning(self):
        order = self.env['sale.order'].new({
            'partner_id': self.partner.id,
            'ks_global_discount_type': 'amount',
            'ks_global_discount_rate': 10.0,
        })

        result = order._onchange_ks_global_discount_rate()

        self.assertIn('warning', result)
        self.assertIn('positive amount', result['warning']['message'])

    def test_discount_percentages_outside_bounds_are_rejected(self):
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        line = self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product.id,
            'name': self.product.display_name,
            'product_uom_qty': 1.0,
            'price_unit': 100.0,
        })
        with self.assertRaises(ValidationError):
            line.write({'discount_2': 101.0})
        with self.assertRaises(ValidationError):
            order.write({
                'ks_global_discount_type': 'percent',
                'ks_global_discount_rate': 101.0,
            })
