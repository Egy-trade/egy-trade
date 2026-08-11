# -*- coding: utf-8 -*-

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import SavepointCase

from ..models.finance_purchase import _PURCHASE_PROVENANCE_TOKEN


class TestPurchaseEstimateControls(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref('base.res_partner_1')
        cls.vendor = cls.env.ref('base.res_partner_2')
        cls.company = cls.env.company
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

    def _provenance_line(self, purchase, sale_line, price_unit=0.0):
        return self.env['purchase.order.line'].create({
            'order_id': purchase.id, 'product_id': self.product.id,
            'name': self.product.display_name, 'product_qty': 1.0,
            'product_uom': self.product.uom_po_id.id, 'price_unit': price_unit,
            'source_sale_line_id': sale_line.id,
            '_finance_purchase_provenance_token': _PURCHASE_PROVENANCE_TOKEN,
        })

    def test_nonzero_estimate_is_kept_as_source_evidence(self):
        sale_line = self._sale_line(25.0)
        purchase = self._purchase_order()
        values = sale_line._purchase_service_prepare_line_values(purchase)
        self.assertEqual(values['source_sale_order_id'], sale_line.order_id.id)
        self.assertEqual(values['source_sale_line_id'], sale_line.id)
        self.assertEqual(values['purchase_estimate_amount'], 25.0)
        self.assertFalse(values['supplier_cost_required'])

    def test_estimate_to_quotation_uses_stored_inverse_rate(self):
        sale_line = self._sale_line(25.0)
        order = sale_line.order_id
        company_currency = self.company.currency_id
        eur = self.env.ref('base.EUR')
        usd = self.env.ref('base.USD')
        estimate_currency = eur if eur != company_currency else usd
        test_date = fields.Date.to_date('2020-01-02')
        self.env['res.currency.rate'].create({
            'name': test_date,
            'rate': 0.5,
            'currency_id': estimate_currency.id,
            'company_id': self.company.id,
        })
        pricelist = self.env['product.pricelist'].create({
            'name': 'UAT estimate quote currency', 'currency_id': company_currency.id,
        })
        order.write({
            'pricelist_id': pricelist.id,
            'currency_estimate_id': estimate_currency.id,
            'date_order': test_date,
        })
        purchase = self._purchase_order()
        purchase.currency_id = order.currency_id
        values = sale_line._purchase_service_prepare_line_values(purchase)
        expected = sale_line.purchase_price_estimate * order.currency_rate_inverse
        wrong_rate_price = sale_line.purchase_price_estimate * order.currency_rate_estimate
        self.assertNotAlmostEqual(order.currency_rate_inverse, order.currency_rate_estimate)
        self.assertAlmostEqual(values['price_unit'], expected)
        self.assertNotAlmostEqual(values['price_unit'], wrong_rate_price)

    def test_mto_procurement_carries_the_source_sale_line(self):
        sale_line = self._sale_line(25.0)
        values = sale_line._prepare_procurement_values()
        self.assertEqual(values['sale_line_id'], sale_line.id)

    def test_mto_candidate_and_existing_line_keep_quote_provenance(self):
        first_sale_line = self._sale_line(25.0)
        second_sale_line = self._sale_line(30.0)
        purchase = self._purchase_order()
        first_line = self._provenance_line(purchase, first_sale_line)
        base_values = {
            'propagate_cancel': True,
            'orderpoint_id': False,
            'move_dest_ids': self.env['stock.move'],
        }
        second_values = second_sale_line._prepare_procurement_values()
        second_values.update(base_values)
        second_candidate = first_line._find_candidate(
            self.product, 1.0, self.product.uom_po_id, False, 'MTO', 'UAT-MTO',
            self.company, second_values,
        )
        self.assertFalse(second_candidate)
        first_values = first_sale_line._prepare_procurement_values()
        first_values.update(base_values)
        first_candidate = first_line._find_candidate(
            self.product, 1.0, self.product.uom_po_id, False, 'MTO', 'UAT-MTO',
            self.company, first_values,
        )
        self.assertEqual(first_candidate, first_line)
        supplier = self.env['product.supplierinfo'].create({
            'partner_id': self.vendor.id,
            'product_tmpl_id': self.product.product_tmpl_id.id,
            'price': 99.0,
        })
        first_values['supplier'] = supplier
        update_values = self.env['stock.rule']._update_purchase_order_line(
            self.product, 1.0, self.product.uom_po_id, self.company,
            first_values, first_line,
        )
        self.assertAlmostEqual(update_values['price_unit'], first_line.price_unit)

    def test_mto_batch_merging_groups_only_the_same_source_line(self):
        first_sale_line = self._sale_line(25.0)
        second_sale_line = self._sale_line(30.0)
        location = self.env['stock.location'].search([('usage', '=', 'internal')], limit=1)
        Procurement = self.env['procurement.group'].Procurement

        def procurement_for(sale_line):
            values = sale_line._prepare_procurement_values()
            values.update({
                'propagate_cancel': True,
                'product_description_variants': False,
                'orderpoint_id': False,
                'move_dest_ids': self.env['stock.move'],
            })
            return Procurement(
                self.product, 1.0, self.product.uom_po_id, location,
                'MTO', 'UAT-MTO', self.company, values,
            )

        first = procurement_for(first_sale_line)
        second = procurement_for(second_sale_line)
        rule = self.env['stock.rule']
        self.assertEqual(len(rule._get_procurements_to_merge([first, second])), 2)
        self.assertEqual(len(rule._get_procurements_to_merge([first, procurement_for(first_sale_line)])), 1)

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
