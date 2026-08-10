# -*- coding: utf-8 -*-
"""Regression contract for canonical quotation Product Pricing lines.

`sale.order.order_line` is the only authoritative collection.  This suite
guards against the former duplicate Product Pricing one2many which could retain
a deleted line and later fail during preview/apply.
"""

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import Form, SavepointCase


class ProductPricingCase(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref('base.res_partner_1')
        cls.product = cls.env['product.product'].create({
            'name': 'Pricing regression product', 'sale_ok': True,
            'purchase_ok': True, 'list_price': 100.0, 'standard_price': 50.0,
        })
        cls.other_product = cls.env['product.product'].create({
            'name': 'Replacement pricing product', 'sale_ok': True,
            'purchase_ok': True, 'list_price': 75.0, 'standard_price': 35.0,
        })
        cls.pricing_user = cls.env['res.users'].create({
            'name': 'Regression Product Pricing User',
            'login': 'regression.pricing.user@example.test',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('sales_team.group_sale_salesman').id,
                cls.env.ref('sale_order_product_pricing.product_pricing_group').id,
            ])],
        })

    def _order(self, global_factor=1.20):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id, 'global_factor': global_factor,
            'product_pricing': True,
            'user_id': self.pricing_user.id,
        })

    def _line(self, order, product=None, cost=50.0, price=None):
        product = product or self.product
        return self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': product.id,
            'name': product.display_name, 'product_uom_qty': 1.0,
            'price_unit': product.list_price if price is None else price,
            'purchase_price_estimate': cost,
        })

    def _preview(self, order):
        return order.action_preview_product_pricing()

    def _apply(self, order):
        return order.with_context(pricing_apply_confirmed=True).action_apply_product_pricing()

    def _warning(self, line):
        preview = line.order_id.get_product_pricing_preview()['lines']
        item = next(item for item in preview if item['line_id'] == line.id)
        return str(item.get('reason') or '')

    def _preview_item(self, line):
        preview = line.order_id.get_product_pricing_preview()['lines']
        return next(item for item in preview if item['line_id'] == line.id)

    def _has_audit(self, order, fragment):
        return bool(order.pricing_audit_log_ids.filtered(
            lambda event: fragment.lower() in (event.reason or '').lower()
        ))

    def test_01_order_line_is_canonical_and_duplicate_pricing_collection_is_removed(self):
        order = self._order()
        self._line(order)
        self.assertIn('order_line', order._fields)
        self.assertNotIn('product_pricing_ids', order._fields)

    def test_02_bulk_delete_edit_create_uses_only_surviving_order_lines(self):
        order = self._order()
        deleted = self._line(order)
        surviving = self._line(order, self.other_product)
        self._preview(order)

        deleted.unlink()
        surviving.write({'purchase_price_estimate': 42.0})
        created = self._line(order, cost=60.0)
        self._preview(order)
        self._apply(order)

        self.assertEqual(set(order.order_line.ids), set((surviving | created).ids))
        self.assertNotIn(deleted.id, order.order_line.ids)
        self.assertTrue(all(line.price_origin == 'product_pricing' for line in order.order_line))

    def test_03_new_line_inherits_global_factor_but_starts_from_pricelist(self):
        order = self._order(global_factor=1.35)
        line = self._line(order)
        self.assertAlmostEqual(line.factor, 1.35)
        self.assertEqual(line.price_origin, 'pricelist')
        self.assertIn('price_reference', line._fields)

    def test_04_zero_cost_is_ineligible_and_apply_skips_with_explanation(self):
        order = self._order()
        line = self._line(order, cost=0.0)
        line.write({'factor': 0.0})
        before = line.price_unit
        self._preview(order)
        self.assertEqual(self._preview_item(line)['status'], 'skipped')
        self.assertIn('cost', self._warning(line).lower())
        self.assertFalse(line.pricing_eligible)
        self.assertTrue(line.pricing_warning)
        self._apply(order)
        self.assertEqual(line.price_unit, before)
        self.assertEqual(line.price_origin, 'pricelist')

    def test_05_positive_to_zero_reverts_to_pricelist_with_warning_and_audit(self):
        order = self._order()
        line = self._line(order, cost=50.0)
        self._preview(order)
        self._apply(order)
        line.write({'purchase_price_estimate': 0.0})
        self._preview(order)
        self.assertEqual(line.price_origin, 'pricelist')
        self.assertIn('cost', self._warning(line).lower())
        self.assertFalse(line.pricing_eligible)
        self.assertTrue(line.pricing_warning)
        self.assertTrue(self._has_audit(order, 'changed to zero'))

    def test_06_zero_to_positive_stays_pricelist_until_apply(self):
        order = self._order()
        line = self._line(order, cost=0.0)
        self._preview(order)
        line.write({'purchase_price_estimate': 50.0})
        self._preview(order)
        self.assertTrue(line.pricing_eligible)
        self.assertFalse(line.pricing_warning)
        self.assertEqual(line.price_origin, 'pricelist')
        self._apply(order)
        self.assertEqual(line.price_origin, 'product_pricing')

    def test_07_negative_cost_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._line(self._order(), cost=-0.01)

    def test_08_authorized_manual_price_is_edited_and_survives_recompute(self):
        line = self._line(self._order())
        self._preview(line.order_id)
        self._apply(line.order_id)
        line.with_user(self.pricing_user).write({'price_unit': 137.0})
        self.assertEqual(line.price_origin, 'edited')
        line.write({'purchase_price_estimate': 55.0})
        self._preview(line.order_id)
        self.assertEqual(line.price_unit, 137.0)
        self.assertEqual(line.price_origin, 'edited')

    def test_09_apply_is_atomic_for_incomplete_attempted_product_pricing(self):
        order = self._order()
        priced = self._line(order, cost=50.0)
        incomplete = self._line(order, self.other_product, cost=50.0)
        # Model a legacy/imported invalid row without violating Odoo's
        # accountable-line constraint or exposing an RPC bypass flag. Apply
        # must reject the batch before changing the otherwise ready line.
        self.env.cr.execute(
            'UPDATE sale_order_line SET factor = %s WHERE id = %s',
            [0.0, incomplete.id],
        )
        self.env.invalidate_all()
        before = priced.price_unit
        self._preview(order)
        with self.assertRaises(UserError):
            self._apply(order)
        self.assertEqual(priced.price_unit, before)
        self.assertEqual(priced.price_origin, 'pricelist')
        self.assertEqual(self._preview_item(incomplete)['status'], 'blocked')

    def test_10_product_or_uom_replacement_requires_preview_before_apply(self):
        order = self._order()
        line = self._line(order)
        self._preview(order)
        line.write({
            'product_id': self.other_product.id,
            'product_uom': self.env.ref('uom.product_uom_dozen').id,
        })
        self.assertTrue(line.pricing_reprice_pending)
        with self.assertRaises(UserError):
            self._apply(order)
        self._preview(order)
        self.assertEqual(self._preview_item(line)['status'], 'ready')
        self._apply(order)
        self.assertEqual(line.product_id, self.other_product)
        self.assertEqual(line.product_uom, self.env.ref('uom.product_uom_dozen'))
        self.assertEqual(line.price_origin, 'product_pricing')
        self.assertFalse(line.pricing_reprice_pending)

    def test_11_currency_pricelist_reprices_edited_line_only_after_confirmed_apply(self):
        order = self._order()
        line = self._line(order)
        self._preview(order)
        self._apply(order)
        line.with_user(self.pricing_user).write({'price_unit': 137.0})
        old_currency = order.currency_id
        edited_price = line.price_unit
        self.assertEqual(line.price_origin, 'edited')
        self.assertEqual(line.price_currency_id, old_currency)

        target_currency = (
            self.env.ref('base.EUR')
            if old_currency == self.env.ref('base.USD')
            else self.env.ref('base.USD')
        )
        converted_pricelist = self.env['product.pricelist'].create({
            'name': 'Regression Converted-Currency Pricing',
            'currency_id': target_currency.id,
        })
        order.with_user(self.pricing_user).write({'pricelist_id': converted_pricelist.id})
        self.assertEqual(order.pricelist_id, converted_pricelist)
        self.assertEqual(line.price_unit, edited_price)
        self.assertEqual(line.price_origin, 'edited')
        self.assertEqual(line.price_currency_id, old_currency)

        self._preview(order)
        item = self._preview_item(line)
        self.assertEqual(item['status'], 'protected')
        self.assertTrue(item['conversion_required'])
        self.assertIn('proposed_price', item)
        self._apply(order)

        self.assertEqual(line.price_origin, 'edited')
        self.assertEqual(line.price_currency_id, converted_pricelist.currency_id)
        self.assertAlmostEqual(line.price_unit, item['proposed_price'])
        conversion_events = order.pricing_audit_log_ids.filtered(
            lambda event: 'currency conversion' in (event.reason or '').lower()
        )
        self.assertTrue(conversion_events)
        self.assertTrue(any(abs(event.old_price - edited_price) < 1e-6 for event in conversion_events))
        self.assertTrue(any(
            abs(event.new_price - item['proposed_price']) < 1e-6
            for event in conversion_events
        ))
        self.assertTrue(any(event.old_currency_id == old_currency for event in conversion_events))
        self.assertTrue(any(
            event.new_currency_id == converted_pricelist.currency_id
            for event in conversion_events
        ))

    def test_12_origin_counts_and_order_audit_log_are_complete(self):
        order = self._order()
        calculated = self._line(order, cost=50.0)
        pricelist = self._line(order, self.other_product, cost=0.0)
        self._preview(order)
        self.assertEqual(order.product_pricing_line_count, 0)
        self.assertEqual(order.odoo_pricelist_line_count, 2)
        self.assertEqual(order.edited_price_line_count, 0)
        self.assertTrue(self._has_audit(order, 'product pricing preview'))
        self.assertEqual(self._preview_item(calculated)['status'], 'ready')
        self.assertEqual(self._preview_item(pricelist)['status'], 'skipped')
        self._apply(order)
        self.assertEqual(order.product_pricing_line_count, 1)
        self.assertEqual(order.odoo_pricelist_line_count, 1)

    def test_13_form_creation_leaves_a_single_canonical_line(self):
        with Form(self.env['sale.order'].with_user(self.pricing_user)) as form:
            form.partner_id = self.partner
            form.product_pricing = True
        order = form.save()
        line = self._line(order)
        self._preview(order)
        self.assertEqual(order.order_line, line)

    def test_14_zero_cost_product_replacement_applies_pricelist_after_preview(self):
        order = self._order()
        line = self._line(order, cost=0.0)
        old_price = line.price_unit
        line.write({'product_id': self.other_product.id})
        self.assertEqual(line.price_unit, old_price)
        self._preview(order)
        item = self._preview_item(line)
        self.assertEqual(item['status'], 'skipped')
        self.assertTrue(item['reprice_required'])
        self._apply(order)
        self.assertEqual(line.price_origin, 'pricelist')
        self.assertEqual(line.price_unit, item['proposed_price'])

    def test_15_product_replacement_reprices_even_when_old_price_was_edited(self):
        order = self._order()
        line = self._line(order)
        self._preview(order)
        self._apply(order)
        line.with_user(self.pricing_user).write({'price_unit': 137.0})
        line.write({'product_id': self.other_product.id})

        self.assertEqual(line.price_unit, 137.0)
        self.assertEqual(line.price_origin, 'edited')
        self.assertTrue(line.pricing_reprice_pending)
        self._preview(order)
        item = self._preview_item(line)
        self.assertEqual(item['status'], 'ready')
        self._apply(order)

        self.assertEqual(line.price_unit, item['proposed_price'])
        self.assertEqual(line.price_origin, 'product_pricing')
        self.assertFalse(line.pricing_reprice_pending)

    def test_16_preview_opens_detailed_review_wizard(self):
        order = self._order()
        self._line(order, cost=0.0)
        action = self._preview(order)

        self.assertEqual(action['res_model'], 'sale.order.pricing.preview')
        wizard = self.env[action['res_model']].browse(action['res_id'])
        self.assertEqual(wizard.skipped_count, 1)
        self.assertEqual(wizard.line_ids.status, 'skipped')
        self.assertTrue(wizard.line_ids.reason)

    def test_17_global_factor_requires_fresh_preview_and_preserves_line_factor(self):
        order = self._order(global_factor=1.20)
        line = self._line(order)
        line.write({'line_factor': 1.10})
        original_price = line.price_unit
        self._preview(order)

        order.with_user(self.pricing_user).write({'global_factor': 1.50})
        self.assertAlmostEqual(line.factor, 1.50)
        self.assertAlmostEqual(line.line_factor, 1.10)
        self.assertEqual(line.price_unit, original_price)
        with self.assertRaises(UserError):
            self._apply(order)

        self._preview(order)
        proposed_price = self._preview_item(line)['proposed_price']
        self._apply(order)
        self.assertAlmostEqual(line.price_unit, proposed_price)
        self.assertEqual(line.price_origin, 'product_pricing')

    def test_18_public_initializing_context_cannot_bypass_pricing_constraints(self):
        order = self._order()
        line = self._line(order)

        with self.assertRaises(ValidationError):
            line.with_context(pricing_initializing=True).write({'factor': 0.0})

    def test_19_product_replacement_ignores_simultaneous_manual_price(self):
        order = self._order()
        line = self._line(order)
        old_price = line.price_unit

        line.with_user(self.pricing_user).write({
            'product_id': self.other_product.id,
            'price_unit': 999.0,
        })

        self.assertEqual(line.price_unit, old_price)
        self.assertTrue(line.pricing_reprice_pending)
