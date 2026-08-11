# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import SavepointCase

from ..models.finance_purchase import _PURCHASE_PROVENANCE_TOKEN


class TestPurchaseEstimateControls(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref('base.res_partner_1')
        cls.vendor = cls.env.ref('base.res_partner_2')
        cls.product = cls.env['product.product'].create({
            'name': 'Purchase estimate control product', 'sale_ok': True,
            'purchase_ok': True, 'list_price': 100.0,
        })

    def _sale_line(self, estimate):
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        if hasattr(order, '_record_commercial_change'):
            order._record_commercial_change('update_today')
        return self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': self.product.id,
            'name': self.product.display_name, 'product_uom_qty': 1.0,
            'price_unit': 100.0, 'purchase_price_estimate': estimate,
        })

    def _purchase_order(self):
        return self.env['purchase.order'].create({'partner_id': self.vendor.id})

    def test_nonzero_estimate_is_kept_as_source_evidence(self):
        sale_line = self._sale_line(25.0)
        purchase = self._purchase_order()
        values = sale_line._purchase_service_prepare_line_values(purchase)
        self.assertEqual(values['source_sale_order_id'], sale_line.order_id.id)
        self.assertEqual(values['source_sale_line_id'], sale_line.id)
        self.assertEqual(values['purchase_estimate_amount'], 25.0)
        self.assertFalse(values['supplier_cost_required'])

    def test_mto_procurement_carries_the_source_sale_line(self):
        sale_line = self._sale_line(25.0)
        values = sale_line._prepare_procurement_values()
        self.assertEqual(values['sale_line_id'], sale_line.id)

    def test_zero_estimate_uses_positive_vendor_fallback_without_confirmation_block(self):
        sale_line = self._sale_line(0.0)
        purchase = self._purchase_order()
        line = self.env['purchase.order.line'].create({
            'order_id': purchase.id, 'product_id': self.product.id,
            'name': self.product.display_name, 'product_qty': 1.0,
            'product_uom': self.product.uom_po_id.id, 'price_unit': 17.0,
            'source_sale_line_id': sale_line.id,
            '_finance_purchase_provenance_token': _PURCHASE_PROVENANCE_TOKEN,
        })
        self.assertFalse(line.supplier_cost_required)

    def test_zero_estimate_zero_vendor_cost_blocks_confirmation_and_requires_reason(self):
        sale_line = self._sale_line(0.0)
        purchase = self._purchase_order()
        with self.assertRaises(AccessError):
            self.env['purchase.order.line'].create({
                'order_id': purchase.id, 'product_id': self.product.id,
                'name': self.product.display_name, 'product_qty': 1.0,
                'product_uom': self.product.uom_po_id.id, 'price_unit': 20.0,
                'source_sale_line_id': sale_line.id,
                'purchase_estimate_amount': 20.0,
            })
        line = self.env['purchase.order.line'].create({
            'order_id': purchase.id, 'product_id': self.product.id,
            'name': self.product.display_name, 'product_qty': 1.0,
            'product_uom': self.product.uom_po_id.id, 'price_unit': 0.0,
            'source_sale_line_id': sale_line.id,
            '_finance_purchase_provenance_token': _PURCHASE_PROVENANCE_TOKEN,
        })
        self.assertTrue(line.supplier_cost_required)
        with self.assertRaises(AccessError):
            line.write({'purchase_estimate_amount': 20.0})
        with self.assertRaises(AccessError):
            line.write({'source_sale_line_id': False})
        with self.assertRaises(UserError):
            purchase.button_confirm()
        with self.assertRaises(AccessError):
            line.write({'supplier_cost_required': False})
        with self.assertRaises(ValidationError):
            line.write({'price_unit': 20.0})
        line.write({'price_unit': 20.0, 'supplier_cost_reason': 'Written vendor quotation received.'})
        self.assertFalse(line.supplier_cost_required)
        self.assertEqual(line.supplier_cost_recorded_by, self.env.user)
        self.assertTrue(line.supplier_cost_recorded_at)
        audit_count = len(purchase.message_ids)
        line.write({'price_unit': 21.0})
        self.assertEqual(len(purchase.message_ids), audit_count)
