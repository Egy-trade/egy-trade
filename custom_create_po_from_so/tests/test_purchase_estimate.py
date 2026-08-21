from odoo.tests.common import SavepointCase

from ..models.stock_rule import _purchase_estimate_price


class PurchaseEstimateCase(SavepointCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id
        cls.customer = cls.env['res.partner'].create({
            'name': 'Purchase Estimate Customer',
            'customer_rank': 1,
        })
        cls.vendor = cls.env['res.partner'].create({
            'name': 'Purchase Estimate Vendor',
            'supplier_rank': 1,
        })
        unit = cls.env.ref('uom.product_uom_unit')
        cls.product = cls.env['product.product'].create({
            'name': 'Purchased Service Fixture',
            'type': 'service',
            'service_to_purchase': True,
            'sale_ok': True,
            'purchase_ok': True,
            'uom_id': unit.id,
            'uom_po_id': unit.id,
        })
        cls.env['product.supplierinfo'].create({
            'partner_id': cls.vendor.id,
            'product_tmpl_id': cls.product.product_tmpl_id.id,
            'currency_id': cls.currency.id,
            'min_qty': 1.0,
            'price': 80.0,
            'delay': 0,
        })

    def _line(self, purchase_estimate):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'currency_id': self.currency.id,
            'currency_estimate_id': self.currency.id,
        })
        line = self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product.id,
            'name': self.product.display_name,
            'product_uom': self.product.uom_id.id,
            'product_uom_qty': 1.0,
            'purchase_price_estimate': purchase_estimate,
        })
        return order, line

    def _draft_po(self):
        return self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'currency_id': self.currency.id,
            'company_id': self.company.id,
        })

    def test_positive_estimate_seeds_service_purchase_line(self):
        _order, line = self._line(55.0)

        values = line._purchase_service_prepare_line_values(self._draft_po())

        self.assertAlmostEqual(values['price_unit'], 55.0)

    def test_zero_estimate_keeps_standard_vendor_price(self):
        _order, line = self._line(0.0)

        values = line._purchase_service_prepare_line_values(self._draft_po())

        self.assertAlmostEqual(values['price_unit'], 80.0)

    def test_stock_procurement_price_hook_uses_estimate_or_standard_fallback(self):
        _order, estimated_line = self._line(55.0)
        _zero_order, zero_line = self._line(0.0)
        purchase_order = self._draft_po()

        self.assertAlmostEqual(
            _purchase_estimate_price(
                {'sale_line_id': estimated_line.id}, purchase_order,
            ),
            55.0,
        )
        self.assertFalse(_purchase_estimate_price(
            {'sale_line_id': zero_line.id}, purchase_order,
        ))

    def test_stock_estimate_uses_quotation_currency_when_estimate_currency_empty(self):
        order, estimated_line = self._line(55.0)
        order.currency_estimate_id = False

        price = _purchase_estimate_price(
            {'sale_line_id': estimated_line.id}, self._draft_po(),
        )

        self.assertAlmostEqual(price, 55.0)

    def test_service_creation_reuses_draft_po_and_does_not_duplicate(self):
        _order, line = self._line(55.0)
        existing_po = self._draft_po()

        result = line._purchase_service_create()
        purchase_line = result[line]

        self.assertEqual(purchase_line.order_id, existing_po)
        self.assertAlmostEqual(purchase_line.price_unit, 55.0)
        self.assertEqual(len(existing_po.order_line), 1)

        line.invalidate_cache(
            fnames=['purchase_line_ids', 'purchase_line_count'],
        )
        duplicate_result = line._purchase_service_generation()

        self.assertFalse(duplicate_result)
        self.assertEqual(len(existing_po.order_line), 1)
