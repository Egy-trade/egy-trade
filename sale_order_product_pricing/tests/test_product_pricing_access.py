# -*- coding: utf-8 -*-

from lxml import etree

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError

from ..models.sale_order import _PRICING_INTERNAL_TOKEN
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
        manager = cls.env.ref('sales_team.group_sale_manager')
        purchase_group = cls.env.ref('purchase.group_purchase_user')
        cls.quotation_specialist = cls.env['res.users'].create({
            'name': 'Quotation Specialist', 'login': 'quotation.specialist@example.test',
            'groups_id': [(6, 0, [
                base_group.id, sales_group.id,
                cls.env.ref('sale_order_product_pricing.quotation_specialist_group').id,
            ])],
            'max_discount': 30.0,
        })
        cls.pricing_user = cls.env['res.users'].create({
            'name': 'Product Pricing User', 'login': 'pricing.user@example.test',
            'groups_id': [(6, 0, [
                base_group.id, sales_group.id,
                cls.env.ref('sale_order_product_pricing.product_pricing_group').id,
            ])],
            'max_discount': 0.0,
        })
        cls.basic_user = cls.env['res.users'].create({
            'name': 'Basic Sales User', 'login': 'basic.sales@example.test',
            'groups_id': [(6, 0, [base_group.id, sales_group.id])],
            'max_discount': 30.0,
        })
        cls.sales_manager = cls.env['res.users'].create({
            'name': 'Pricing Sales Manager',
            'login': 'pricing.manager@example.test',
            'groups_id': [(6, 0, [base_group.id, manager.id])],
            'max_discount': 0.0,
        })
        cls.other_sales_user = cls.env['res.users'].create({
            'name': 'Unassigned Sales User',
            'login': 'unassigned.sales@example.test',
            'groups_id': [(6, 0, [base_group.id, sales_group.id])],
            'max_discount': 30.0,
        })
        cls.ordinary_reader = cls.env['res.users'].create({
            'name': 'Ordinary Internal Reader',
            'login': 'ordinary.reader@example.test',
            'groups_id': [(6, 0, [base_group.id])],
        })
        cls.purchase_user = cls.env['res.users'].create({
            'name': 'Purchase Only User',
            'login': 'purchase.only@example.test',
            'groups_id': [(6, 0, [base_group.id, purchase_group.id])],
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
        order = self.env['sale.order'].create(values)
        self._record_commercial_change_if_available(order)
        return order

    @staticmethod
    def _record_commercial_change_if_available(order):
        if hasattr(order, '_record_commercial_change'):
            order._record_commercial_change('update_today')

    def _line(self, order):
        return self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': self.product.id,
            'name': self.product.display_name, 'product_uom_qty': 1, 'price_unit': 100,
            'purchase_price_estimate': 50,
        })

    def _option(self, order):
        return self.env['sale.order.option'].create({
            'order_id': order.id,
            'product_id': self.product.id,
            'name': self.product.display_name,
            'quantity': 1.0,
            'uom_id': self.product.uom_id.id,
            'price_unit': self.product.list_price,
        })

    def _preview(self, order):
        return order.with_user(self.pricing_user).action_preview_product_pricing()

    @staticmethod
    def _set_sent(order):
        if 'issued_offer_attachment_id' in order._fields:
            from odoo.addons.sale_revision_history.models.sale_order import (
                _LIFECYCLE_INTERNAL_TOKEN,
            )
            order.with_context(
                _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
            ).write({'state': 'sent'})
        else:
            order.write({'state': 'sent'})

    def _apply(self, order):
        action = self._preview(order)
        wizard = self.env[action['res_model']].browse(action['res_id'])
        return wizard.with_user(self.pricing_user).action_confirm_apply()

    def test_quotation_specialist_can_change_salesperson_only_on_draft_or_revision(self):
        order = self._order(owner=self.quotation_specialist)
        order.with_user(self.quotation_specialist).write({'user_id': self.other_sales_user.id})
        revision = order.copy({'state': 'draft'})
        self._record_commercial_change_if_available(revision)
        revision.with_user(self.quotation_specialist).write({'user_id': self.other_sales_user.id})

        for state in ('sent', 'sale'):
            locked_order = self._order(owner=self.quotation_specialist)
            if state == 'sent':
                self._set_sent(locked_order)
            else:
                locked_order.write({'state': state})
            with self.assertRaises(UserError):
                locked_order.with_user(self.quotation_specialist).write({
                    'user_id': self.env.user.id,
                })

    def test_legacy_draft_backfills_specialist_before_salesperson_assignment(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'user_id': self.quotation_specialist.id,
            'quotation_specialist_id': False,
        })
        self._record_commercial_change_if_available(order)

        order.with_user(self.quotation_specialist).write({'user_id': self.pricing_user.id})

        self.assertEqual(order.user_id, self.pricing_user)
        self.assertEqual(order.quotation_specialist_id, self.quotation_specialist)

    def test_quotation_specialist_can_create_and_edit_non_price_line_content(self):
        order = self.env['sale.order'].with_user(self.quotation_specialist).create({
            'partner_id': self.partner.id,
            'user_id': self.quotation_specialist.id,
        })
        self.assertEqual(order.quotation_specialist_id, self.quotation_specialist)
        self._record_commercial_change_if_available(
            order.with_user(self.quotation_specialist)
        )
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

        purchase_model = self.env['purchase.order']
        purchase_order = purchase_model.create({'partner_id': self.partner.id})
        purchase_line = self.env['purchase.order.line'].create({
            'order_id': purchase_order.id,
            'product_id': self.product.id,
            'name': 'Initial linked purchase description',
            'product_qty': 1.0,
            'product_uom': self.product.uom_po_id.id,
            'date_planned': fields.Datetime.now(),
            'price_unit': 1.0,
            'sale_line_id': line.id,
        })
        line.with_user(self.quotation_specialist).write({
            'name': 'Synchronized quotation description',
        })
        self.assertEqual(purchase_line.name, 'Synchronized quotation description')

        specialist_purchase_model = purchase_model.with_user(self.quotation_specialist)
        specialist_purchase_line_model = self.env['purchase.order.line'].with_user(
            self.quotation_specialist
        )
        for protected_model in (specialist_purchase_model, specialist_purchase_line_model):
            for operation in ('read', 'create', 'write'):
                with self.assertRaises(AccessError):
                    protected_model.check_access_rights(operation, raise_exception=True)
        with self.assertRaises(AccessError):
            specialist_purchase_model.create({'partner_id': self.partner.id})
        with self.assertRaises(AccessError):
            specialist_purchase_model.browse(purchase_order.id).write({
                'partner_ref': 'Quotation specialist must not edit purchases',
            })

    def test_quotation_specialist_explicit_unassigned_normalizes_to_self(self):
        order = self.env['sale.order'].with_user(self.quotation_specialist).create({
            'partner_id': self.partner.id,
            'user_id': self.quotation_specialist.id,
            'quotation_specialist_id': False,
        })

        self.assertEqual(order.quotation_specialist_id, self.quotation_specialist)

    def test_quotation_specialist_cannot_price_or_manually_edit_price(self):
        order = self._order(owner=self.quotation_specialist)
        line = self._line(order)
        with self.assertRaises(AccessError):
            order.with_user(self.quotation_specialist).action_preview_product_pricing()
        with self.assertRaises(AccessError):
            order.with_user(self.quotation_specialist).with_context(
                pricing_apply_confirmed=True
            ).action_apply_product_pricing()
        with self.assertRaises(UserError):
            line.with_user(self.quotation_specialist).write({'price_unit': 90.0})

    def test_product_pricing_user_can_preview_apply_and_edit_price(self):
        order = self._order()
        line = self._line(order)
        self._apply(order)
        self._apply(order)
        line.with_user(self.pricing_user).write({'price_unit': 90.0})
        self.assertEqual(line.price_origin, 'edited')

    def test_non_specialist_cannot_override_manual_price(self):
        order = self._order(owner=self.basic_user)
        line = self._line(order)
        with self.assertRaises(UserError):
            line.with_user(self.basic_user).write({'price_unit': 90.0})
        with self.assertRaises(AccessError):
            line.with_user(self.basic_user).write({'discount_2': 5.0})
        with self.assertRaises(AccessError):
            self._order(owner=self.quotation_specialist).with_user(
                self.quotation_specialist
            ).write({
                'ks_global_discount_rate': 5.0,
            })

    def test_rpc_context_cannot_forge_internal_pricing_authority(self):
        order = self._order(owner=self.quotation_specialist)
        line = self._line(order)
        with self.assertRaises(UserError):
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
        with self.assertRaises(AccessError):
            order.with_user(self.quotation_specialist).write({
                'pricelist_id': self.env.ref('product.list0').id,
            })

    def test_state_lock_blocks_pricing_user_after_send_or_confirmation(self):
        order = self._order()
        line = self._line(order)
        for state in ('sent', 'sale'):
            if state == 'sent':
                self._set_sent(order)
            else:
                order.write({'state': state})
            with self.assertRaises(UserError):
                order.with_user(self.pricing_user).action_preview_product_pricing()
            with self.assertRaises(UserError):
                line.with_user(self.pricing_user).write({'price_unit': 90.0})
            with self.assertRaises(UserError):
                line.with_user(self.pricing_user).write({'name': 'Post-send mutation'})
            with self.assertRaises(UserError):
                order.with_user(self.pricing_user).write({
                    'partner_id': self.env.ref('base.res_partner_2').id,
                })
            with self.assertRaises(UserError):
                order.with_user(self.pricing_user).write({'state': 'draft'})

    def test_state_lock_blocks_template_and_optional_product_mutations(self):
        order = self._order()
        option = self._option(order)
        self._set_sent(order)

        with self.assertRaises(UserError):
            order.write({'sale_order_template_id': False})
        with self.assertRaises(UserError):
            self._option(order)
        with self.assertRaises(UserError):
            option.write({'quantity': 2.0})
        with self.assertRaises(UserError):
            option.unlink()

    def test_state_lock_blocks_moving_a_draft_optional_product_to_sent_order(self):
        source_order = self._order()
        option = self._option(source_order)
        sent_order = self._order()
        self._set_sent(sent_order)

        with self.assertRaises(UserError):
            option.write({'order_id': sent_order.id})
        self.assertEqual(option.order_id, source_order)

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

    def test_sales_manager_can_reach_origin_certification_but_ordinary_sales_cannot(self):
        view_id = self.env.ref('sale.view_order_form').id
        manager_view = self.env['sale.order'].with_user(
            self.sales_manager
        ).fields_view_get(view_id=view_id, view_type='form')
        manager_root = etree.fromstring(manager_view['arch'].encode())
        manager_page = manager_root.xpath("//page[@name='product_pricing']")
        self.assertEqual(len(manager_page), 1)
        self.assertTrue(manager_page[0].xpath(
            ".//button[@name='action_reclassify_historical_origin']"
        ))

        ordinary_view = self.env['sale.order'].with_user(
            self.basic_user
        ).fields_view_get(view_id=view_id, view_type='form')
        ordinary_root = etree.fromstring(ordinary_view['arch'].encode())
        self.assertFalse(ordinary_root.xpath("//page[@name='product_pricing']"))

    def test_product_analysis_is_not_globally_exposed(self):
        analysis_model = self.env['product.analysis']
        analysis_model.with_user(self.pricing_user).search([], limit=1)
        for user in (self.quotation_specialist, self.basic_user):
            with self.assertRaises(AccessError):
                analysis_model.with_user(user).search([], limit=1)

    def test_sent_quotation_view_locks_commercial_header_and_lines(self):
        """Keep the view guard aligned with the immutable-version ORM guard."""
        view = self.env.ref('sale_order_product_pricing.sale_order_product_pricing_form')
        root = etree.fromstring(view.arch_db.encode())
        expected_xpaths = (
            "//field[@name='partner_id']",
            "//field[@name='partner_invoice_id']",
            "//field[@name='partner_shipping_id']",
            "//field[@name='date_order']",
            "//field[@name='validity_date']",
            "//field[@name='pricelist_id']",
            "//field[@name='payment_term_id']",
            "//field[@name='fiscal_position_id']",
            "//field[@name='incoterm']",
            "//field[@name='client_order_ref']",
            "//field[@name='note']",
            "//page[@name='order_lines']/field[@name='order_line']",
        )
        for expression in expected_xpaths:
            node = root.xpath("//xpath[@expr=$expression]", expression=expression)
            self.assertEqual(len(node), 1, expression)
            attrs = node[0].xpath("./attribute[@name='attrs']/text()")
            self.assertEqual(len(attrs), 1, expression)
            self.assertIn("'readonly'", attrs[0], expression)
            self.assertIn("('state', '!=', 'draft')", attrs[0], expression)

    def test_sent_quotation_view_locks_template_and_optional_products(self):
        view = self.env.ref('sale_order_product_pricing.sale_order_template_immutability')
        root = etree.fromstring(view.arch_db.encode())
        for field_name in ('sale_order_template_id', 'sale_order_option_ids'):
            node = root.xpath(
                "//field[@name=$field_name][@position='attributes']",
                field_name=field_name,
            )
            self.assertEqual(len(node), 1, field_name)
            attrs = node[0].xpath("./attribute[@name='attrs']/text()")
            self.assertEqual(len(attrs), 1, field_name)
            self.assertIn("('state', '!=', 'draft')", attrs[0], field_name)

    def test_sent_quotation_view_locks_global_discount_toggle(self):
        view = self.env.ref('sale_order_product_pricing.sale_order_universal_discount_security')
        root = etree.fromstring(view.arch_db.encode())
        node = root.xpath("//field[@name='ks_enable_discount'][@position='attributes']")
        self.assertEqual(len(node), 1)
        attrs = node[0].xpath("./attribute[@name='attrs']/text()")
        self.assertEqual(len(attrs), 1)
        self.assertIn("('state', '!=', 'draft')", attrs[0])
        self.assertIn("('can_edit_quotation_price', '=', False)", attrs[0])

    def test_standard_order_lines_hide_extra_discounts(self):
        view = self.env.ref('sale_order_product_pricing.sale_order_universal_discount_security')
        root = etree.fromstring(view.arch_db.encode())
        standard_tree = "//page[@name='order_lines']/field[@name='order_line']/tree"
        for field_name in ('discount_2', 'discount_3'):
            node = root.xpath(
                "//xpath[@expr=$expression]",
                expression="%s/field[@name='%s']" % (standard_tree, field_name),
            )
            self.assertEqual(len(node), 1, field_name)
            self.assertEqual(
                node[0].xpath("./attribute[@name='invisible']/text()"),
                ['1'],
            )

        standard_discount = root.xpath(
            "//xpath[@expr=$expression]",
            expression="%s/field[@name='discount']" % standard_tree,
        )
        self.assertEqual(len(standard_discount), 1)
        self.assertEqual(
            standard_discount[0].xpath("./attribute[@name='string']/text()"),
            ['Discount %'],
        )

    def test_assigned_specialist_can_delete_draft_line(self):
        order = self._order(owner=self.quotation_specialist)
        line = self._line(order)
        line.with_user(self.quotation_specialist).unlink()
        self.assertFalse(line.exists())

    def test_standard_discount_requires_verified_pricelist_and_uses_30_percent_cap(self):
        if 'standard_discount_enabled' in self.env.company._fields:
            self.env.company.write({
                'standard_discount_enabled': True,
                'standard_discount_maximum': 30.0,
            })
            self.basic_user.write({'standard_discount_cap': 30.0})
        order = self._order(owner=self.basic_user)
        line = self._line(order)
        self.assertTrue(line.price_origin_verified)
        self.assertEqual(line.price_origin_evidence, 'new_pricelist')

        line.with_user(self.basic_user).write({'discount': 30.0})
        self.assertAlmostEqual(line.discount, 30.0)
        with self.assertRaises(ValidationError):
            line.with_user(self.basic_user).write({'discount': 30.01})

        line.sudo().with_context(
            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
        ).write({
            'price_origin': 'product_pricing',
            'price_origin_verified': True,
            'price_origin_evidence': 'product_pricing_apply',
        })
        with self.assertRaises(AccessError):
            line.with_user(self.basic_user).write({'discount': 5.0})

        with self.assertRaises(AccessError):
            self.env['sale.order.line'].with_user(self.basic_user).create({
                'order_id': order.id,
                'product_id': self.product.id,
                'name': self.product.display_name,
                'product_uom_qty': 1.0,
                'standard_discount_override_used': True,
            })

        line.sudo().with_context(
            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
        ).write({
            'price_origin': 'historical_unverified',
            'price_origin_verified': False,
            'price_origin_evidence': 'legacy_unverified',
        })
        with self.assertRaises(AccessError):
            line.with_user(self.basic_user).write({'discount': 5.0})

    def test_only_management_can_override_standard_discount_with_reason(self):
        pricing_order = self._order(owner=self.pricing_user)
        pricing_line = self._line(pricing_order)
        pricing_line.sudo().with_context(
            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
        ).write({
            'price_origin': 'product_pricing',
            'price_origin_verified': True,
            'price_origin_evidence': 'product_pricing_apply',
        })
        self.assertFalse(
            pricing_line.with_user(self.pricing_user).can_edit_pricelist_discount
        )
        with self.assertRaises(AccessError):
            pricing_line.with_user(self.pricing_user).write({'discount': 5.0})

        manager_order = self._order(owner=self.sales_manager)
        manager_line = self._line(manager_order)
        self.sales_manager.write({'standard_discount_cap': 10.0})
        manager_order.with_user(self.sales_manager).write({
            'standard_discount_override_reason': 'Approved manager discount override.',
        })
        manager_line.with_user(self.sales_manager).write({'discount': 15.0})
        self.assertAlmostEqual(manager_line.discount, 15.0)
        self.assertEqual(manager_line.price_origin, 'pricelist')
        self.assertTrue(manager_line.standard_discount_override_used)

    def test_manual_price_and_standard_discount_cannot_share_one_write(self):
        order = self._order(owner=self.sales_manager)
        line = self._line(order)
        original_price = line.price_unit

        with self.assertRaises(AccessError):
            line.with_user(self.sales_manager).write({
                'price_unit': 88.0,
                'discount': 10.0,
            })

        self.assertEqual(line.price_unit, original_price)
        self.assertAlmostEqual(line.discount, 0.0)
        self.assertEqual(line.price_origin, 'pricelist')
        self.assertTrue(line.price_origin_verified)

    def test_manager_can_certify_active_draft_historical_origin_and_audits(self):
        order = self._order(owner=self.basic_user)
        line = self._line(order)
        original_price = line.price_unit
        line.sudo().with_context(
            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
        ).write({
            'price_origin': 'historical_unverified',
            'price_origin_verified': False,
            'price_origin_evidence': 'legacy_unverified',
            'pricing_warning': 'Manager review required.',
        })

        with self.assertRaises(UserError):
            line.with_user(self.basic_user).action_reclassify_historical_origin()
        action = line.with_user(self.sales_manager).action_reclassify_historical_origin()
        self.assertEqual(action['res_model'], 'sale.order.price.origin.reclassify')
        wizard = self.env[action['res_model']].with_user(self.sales_manager).create({
            'line_id': line.id,
            'new_origin': 'product_pricing',
            'reason': 'Signed pricing worksheet PP-001 matches this line.',
        })
        wizard.action_confirm()

        self.assertEqual(line.price_unit, original_price)
        self.assertEqual(line.price_origin, 'product_pricing')
        self.assertTrue(line.price_origin_verified)
        self.assertEqual(line.price_origin_evidence, 'manager_reclassified')
        self.assertFalse(line.pricing_warning)
        self.assertTrue(self.env['sale.order.pricing.audit'].search([
            ('order_id', '=', order.id),
            ('line_id', '=', line.id),
            ('reason', 'ilike', 'Signed pricing worksheet PP-001'),
        ]))

    def test_manager_cannot_certify_historical_origin_on_immutable_sent_line(self):
        order = self._order(owner=self.basic_user)
        line = self._line(order)
        original_price = line.price_unit
        line.sudo().with_context(
            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
        ).write({
            'price_origin': 'historical_unverified',
            'price_origin_verified': False,
            'price_origin_evidence': 'legacy_unverified',
            'pricing_warning': 'Manager review required.',
        })
        self._set_sent(order)

        with self.assertRaises(UserError):
            line.with_user(self.sales_manager).action_reclassify_historical_origin()

        self.assertEqual(line.price_unit, original_price)
        self.assertEqual(line.price_origin, 'historical_unverified')
        self.assertFalse(line.price_origin_verified)
        with self.assertRaises(UserError):
            line.with_user(self.sales_manager).write({'name': 'Sent mutation'})

    def test_manager_cannot_certify_historical_origin_on_archived_draft(self):
        if 'active' not in self.env['sale.order']._fields:
            self.skipTest('Revision history is not installed in this module-only database.')
        order = self._order(owner=self.basic_user)
        line = self._line(order)
        line.sudo().with_context(
            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
        ).write({
            'price_origin': 'historical_unverified',
            'price_origin_verified': False,
            'price_origin_evidence': 'legacy_unverified',
            'pricing_warning': 'Manager review required.',
        })
        action = line.with_user(self.sales_manager).action_reclassify_historical_origin()
        wizard = self.env[action['res_model']].with_user(self.sales_manager).create({
            'line_id': line.id,
            'new_origin': 'product_pricing',
            'reason': 'Archived drafts must remain immutable.',
        })
        order.sudo().write({'active': False})

        with self.assertRaises(UserError):
            line.with_user(self.sales_manager).action_reclassify_historical_origin()
        with self.assertRaises(UserError):
            wizard.action_confirm()
        self.assertEqual(line.price_origin, 'historical_unverified')
        self.assertFalse(line.price_origin_verified)

    def test_standard_and_pricing_views_use_separate_line_fields(self):
        view = self.env.ref('sale_order_product_pricing.sale_order_product_pricing_form')
        root = etree.fromstring(view.arch_db.encode())
        pricing_page = root.xpath("//page[@name='product_pricing']")
        self.assertEqual(len(pricing_page), 1)
        self.assertEqual(
            len(pricing_page[0].xpath(".//field[@name='pricing_line_ids']")), 1
        )
        self.assertFalse(pricing_page[0].xpath(".//field[@name='order_line']"))
        self.assertTrue(
            root.xpath("//field[@name='price_origin_label'][@optional='show']")
        )
        self.assertFalse(root.xpath("//field[@name='sn']"))
        button = root.xpath("//button[@name='action_preview_product_pricing']")
        self.assertEqual(len(button), 1)
        self.assertTrue(button[0].get('help'))
        self.assertFalse(root.xpath("//button[@name='action_apply_product_pricing']"))
        preview_view = self.env.ref(
            'sale_order_product_pricing.sale_order_pricing_preview_form'
        )
        preview_root = etree.fromstring(preview_view.arch_db.encode())
        confirm = preview_root.xpath("//button[@name='action_confirm_apply']")
        self.assertEqual(len(confirm), 1)
        self.assertTrue(confirm[0].get('help'))

    def test_global_tax_selector_replaces_cif_and_line_tax_editing(self):
        """Keep the quotation-level tax UX independent of item tax edits."""
        view = self.env.ref(
            'sale_order_product_pricing.sale_order_finance_controls_form'
        )
        root = etree.fromstring(view.arch_db.encode())

        self.assertTrue(root.xpath("//field[@name='apply_vat']"))
        self.assertTrue(root.xpath("//field[@name='apply_withholding']"))
        self.assertTrue(root.xpath("//field[@name='vat_exemption_reason']"))
        self.assertTrue(root.xpath(
            "//field[@name='tax_selection_review_required'][@invisible='1']"
        ))
        self.assertTrue(root.xpath(
            "//field[@name='tax_id'][@readonly='1']"
        ))
        self.assertFalse(root.xpath("//*[contains(@string, 'Finance Controls')]"))
        self.assertFalse(root.xpath("//*[contains(@string, 'CIF')]"))

        approval_page = root.xpath(
            "//page[@name='commercial_exception_approval']"
        )
        self.assertEqual(len(approval_page), 1)
        self.assertTrue(approval_page[0].xpath(
            ".//button[@name='action_approve_finance_requirements']"
        ))
        evidence_page = root.xpath("//page[@name='withholding_evidence']")
        self.assertEqual(len(evidence_page), 1)
        self.assertEqual(
            evidence_page[0].get('groups'), 'account.group_account_manager'
        )
        self.assertTrue(evidence_page[0].xpath(
            ".//field[@name='withholding_evidence_ids']"
        ))

    def test_assigned_salesperson_can_crud_draft_lines_but_unassigned_cannot(self):
        order = self.env['sale.order'].with_user(self.basic_user).create({
            'partner_id': self.partner.id,
            'user_id': self.basic_user.id,
        })
        self._record_commercial_change_if_available(order.with_user(self.basic_user))
        line = self.env['sale.order.line'].with_user(self.basic_user).create({
            'order_id': order.id,
            'product_id': self.product.id,
            'name': self.product.display_name,
            'product_uom_qty': 1.0,
        })
        line.with_user(self.basic_user).write({'name': 'Assigned edit'})
        self.assertEqual(line.name, 'Assigned edit')

        with self.assertRaises(AccessError):
            line.with_user(self.other_sales_user).write({'name': 'Unassigned edit'})
        with self.assertRaises(AccessError):
            line.with_user(self.other_sales_user).write({'discount': 5.0})

        line.with_user(self.basic_user).unlink()
        self.assertFalse(line.exists())

    def test_ordinary_reader_and_purchase_user_cannot_access_pricing_internals(self):
        for user in (self.ordinary_reader, self.purchase_user):
            available = self.env['sale.order.line'].with_user(user).fields_get([
                'purchase_price_estimate',
                'factor',
                'line_factor',
                'price_reference',
                'price_origin',
                'price_origin_evidence',
            ])
            self.assertFalse(available)
            with self.assertRaises(AccessError):
                self.env['sale.order.line'].with_user(user).check_access_rights(
                    'write', raise_exception=True,
                )

    def test_assigned_specialist_can_use_canonical_one2many_commands(self):
        order = self.env['sale.order'].with_user(self.quotation_specialist).create({
            'partner_id': self.partner.id,
            'user_id': self.quotation_specialist.id,
            'quotation_specialist_id': self.quotation_specialist.id,
        })
        self._record_commercial_change_if_available(
            order.with_user(self.quotation_specialist)
        )
        order.with_user(self.quotation_specialist).write({
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.display_name,
                'product_uom_qty': 1.0,
                'price_unit': 999.0,
            })],
        })
        line = order.order_line
        self.assertEqual(line.price_unit, self.product.list_price)

        order.with_user(self.quotation_specialist).write({
            'order_line': [(1, line.id, {'name': 'Updated through canonical commands'})],
        })
        self.assertEqual(line.name, 'Updated through canonical commands')

        order.with_user(self.quotation_specialist).write({
            'order_line': [(2, line.id, 0)],
        })
        self.assertFalse(line.exists())
