# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import SavepointCase


class TestProductPricingAccess(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref('base.res_partner_1')
        cls.product = cls.env['product.product'].create({
            'name': 'Pricing access product', 'sale_ok': True, 'list_price': 100.0,
        })
        sales_group = cls.env.ref('sales_team.group_sale_salesman')
        base_group = cls.env.ref('base.group_user')
        cls.quotation_specialist = cls.env['res.users'].create({
            'name': 'Quotation Specialist', 'login': 'quotation.specialist@example.test',
            'groups_id': [(6, 0, [
                base_group.id, sales_group.id,
                cls.env.ref('sale_order_product_pricing.quotation_specialist_group').id,
            ])],
        })
        cls.pricing_user = cls.env['res.users'].create({
            'name': 'Product Pricing User', 'login': 'pricing.user@example.test',
            'groups_id': [(6, 0, [
                base_group.id, sales_group.id,
                cls.env.ref('sale_order_product_pricing.product_pricing_group').id,
            ])],
        })
        cls.basic_user = cls.env['res.users'].create({
            'name': 'Basic Sales User', 'login': 'basic.sales@example.test',
            'groups_id': [(6, 0, [base_group.id, sales_group.id])],
        })

    def _order(self, owner=None):
        owner = owner or self.pricing_user
        values = {
            'partner_id': self.partner.id,
            'product_pricing': True,
            'user_id': owner.id,
        }
        if owner == self.quotation_specialist:
            values['quotation_specialist_id'] = owner.id
        return self.env['sale.order'].create(values)

    def _line(self, order):
        return self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': self.product.id,
            'name': self.product.display_name, 'product_uom_qty': 1, 'price_unit': 100,
            'purchase_price_estimate': 50,
        })

    def _preview(self, order):
        return order.with_user(self.pricing_user).action_preview_product_pricing()

    def _apply(self, order):
        return order.with_user(self.pricing_user).with_context(
            pricing_apply_confirmed=True
        ).action_apply_product_pricing()

    def test_quotation_specialist_can_change_salesperson_only_on_draft_or_revision(self):
        order = self._order(owner=self.quotation_specialist)
        order.with_user(self.quotation_specialist).write({'user_id': self.env.user.id})
        revision = order.copy({'state': 'draft'})
        revision.with_user(self.quotation_specialist).write({'user_id': self.env.user.id})

        for state in ('sent', 'sale'):
            order.write({'state': state})
            with self.assertRaises((AccessError, UserError, ValidationError)):
                order.with_user(self.quotation_specialist).write({'user_id': self.env.user.id})

    def test_legacy_draft_backfills_specialist_before_salesperson_assignment(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'user_id': self.quotation_specialist.id,
            'quotation_specialist_id': False,
        })

        order.with_user(self.quotation_specialist).write({'user_id': self.pricing_user.id})

        self.assertEqual(order.user_id, self.pricing_user)
        self.assertEqual(order.quotation_specialist_id, self.quotation_specialist)

    def test_quotation_specialist_can_create_and_edit_non_price_line_content(self):
        order = self.env['sale.order'].with_user(self.quotation_specialist).create({
            'partner_id': self.partner.id,
            'user_id': self.quotation_specialist.id,
        })
        line = self.env['sale.order.line'].with_user(self.quotation_specialist).create({
            'order_id': order.id,
            'product_id': self.product.id,
            'name': self.product.display_name,
            'product_uom_qty': 1.0,
            'price_unit': 999.0,
        })
        self.assertEqual(line.price_unit, self.product.list_price)
        line.with_user(self.quotation_specialist).write({
            'product_uom_qty': 2.0,
            'name': 'Updated quotation description',
        })
        self.assertEqual(line.product_uom_qty, 2.0)
        self.assertEqual(line.name, 'Updated quotation description')

    def test_quotation_specialist_cannot_price_or_manually_edit_price(self):
        order = self._order(owner=self.quotation_specialist)
        line = self._line(order)
        with self.assertRaises((AccessError, UserError, ValidationError)):
            order.with_user(self.quotation_specialist).action_preview_product_pricing()
        with self.assertRaises((AccessError, UserError, ValidationError)):
            order.with_user(self.quotation_specialist).with_context(
                pricing_apply_confirmed=True
            ).action_apply_product_pricing()
        with self.assertRaises((AccessError, UserError, ValidationError)):
            line.with_user(self.quotation_specialist).write({'price_unit': 90.0})

    def test_product_pricing_user_can_preview_apply_and_edit_price(self):
        order = self._order()
        line = self._line(order)
        self._preview(order)
        self._apply(order)
        line.with_user(self.pricing_user).write({'price_unit': 90.0})
        self.assertEqual(line.price_origin, 'edited')

    def test_non_specialist_cannot_override_manual_price(self):
        order = self._order(owner=self.basic_user)
        line = self._line(order)
        with self.assertRaises((AccessError, UserError, ValidationError)):
            line.with_user(self.basic_user).write({'price_unit': 90.0})
        with self.assertRaises((AccessError, UserError, ValidationError)):
            line.with_user(self.basic_user).write({'discount_2': 5.0})
        with self.assertRaises((AccessError, UserError, ValidationError)):
            self._order(owner=self.quotation_specialist).with_user(
                self.quotation_specialist
            ).write({
                'ks_global_discount_rate': 5.0,
            })

    def test_rpc_context_cannot_forge_internal_pricing_authority(self):
        order = self._order(owner=self.quotation_specialist)
        line = self._line(order)
        with self.assertRaises((AccessError, UserError, ValidationError)):
            line.with_user(self.quotation_specialist).with_context(
                pricing_internal=True,
                pricing_automatic_price=True,
            ).write({'price_unit': 90.0})
        old_origin = line.price_origin
        line.with_user(self.quotation_specialist).with_context(
            pricing_internal=True,
            pricing_automatic_price=True,
        ).write({'price_origin': 'product_pricing'})
        self.assertEqual(line.price_origin, old_origin)

        forged_downpayment = self.env['sale.order.line'].with_user(
            self.quotation_specialist
        ).create({
            'order_id': order.id,
            'product_id': self.product.id,
            'name': 'Forged down payment',
            'product_uom_qty': 1.0,
            'price_unit': 999.0,
            'is_downpayment': True,
        })
        self.assertEqual(forged_downpayment.price_unit, self.product.list_price)
        self.assertFalse(forged_downpayment.is_downpayment)

    def test_quotation_specialist_cannot_change_pricelist(self):
        order = self._order(owner=self.quotation_specialist)
        with self.assertRaises((AccessError, UserError, ValidationError)):
            order.with_user(self.quotation_specialist).write({
                'pricelist_id': self.env.ref('product.list0').id,
            })

    def test_state_lock_blocks_pricing_user_after_send_or_confirmation(self):
        order = self._order()
        line = self._line(order)
        for state in ('sent', 'sale'):
            order.write({'state': state})
            with self.assertRaises((AccessError, UserError, ValidationError)):
                order.with_user(self.pricing_user).action_preview_product_pricing()
            with self.assertRaises((AccessError, UserError, ValidationError)):
                line.with_user(self.pricing_user).write({'price_unit': 90.0})
            with self.assertRaises((AccessError, UserError, ValidationError)):
                line.with_user(self.pricing_user).write({'name': 'Post-send mutation'})
            with self.assertRaises((AccessError, UserError, ValidationError)):
                order.with_user(self.pricing_user).write({
                    'partner_id': self.env.ref('base.res_partner_2').id,
                })
            with self.assertRaises((AccessError, UserError, ValidationError)):
                order.with_user(self.pricing_user).write({'state': 'draft'})

    def test_pricing_audit_is_visible_only_to_product_pricing_users(self):
        order = self._order()
        self._line(order)
        self._preview(order)
        audit_model = self.env['sale.order.pricing.audit']
        self.assertTrue(audit_model.with_user(self.pricing_user).search([
            ('order_id', '=', order.id),
        ]))
        for user in (self.quotation_specialist, self.basic_user):
            with self.assertRaises(AccessError):
                audit_model.with_user(user).search([('order_id', '=', order.id)])

    def test_product_analysis_is_not_globally_exposed(self):
        analysis_model = self.env['product.analysis']
        analysis_model.with_user(self.pricing_user).search([], limit=1)
        for user in (self.quotation_specialist, self.basic_user):
            with self.assertRaises(AccessError):
                analysis_model.with_user(user).search([], limit=1)
