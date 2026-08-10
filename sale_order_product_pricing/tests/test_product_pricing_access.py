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
        return self.env['sale.order'].create(values)

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
            with self.assertRaises(UserError):
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
        self._preview(order)
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
        order.write({'state': 'sent'})

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
        sent_order.write({'state': 'sent'})

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
    def test_assigned_specialist_can_delete_draft_line(self):
        order = self._order(owner=self.quotation_specialist)
        line = self._line(order)
        line.with_user(self.quotation_specialist).unlink()
        self.assertFalse(line.exists())

    def test_standard_discount_requires_verified_pricelist_and_uses_30_percent_cap(self):
        order = self._order(owner=self.basic_user)
        line = self._line(order)
        self.assertTrue(line.price_origin_verified)
        self.assertEqual(line.price_origin_evidence, 'new_pricelist')

        line.with_user(self.basic_user).write({'discount': 30.0})
        self.assertEqual(line.discount, 30.0)
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

        line.sudo().with_context(
            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
        ).write({
            'price_origin': 'historical_unverified',
            'price_origin_verified': False,
            'price_origin_evidence': 'legacy_unverified',
        })
        with self.assertRaises(AccessError):
            line.with_user(self.basic_user).write({'discount': 5.0})

    def test_pricing_user_and_manager_have_full_draft_pricing_authority(self):
        pricing_order = self._order(owner=self.pricing_user)
        pricing_line = self._line(pricing_order)
        pricing_line.sudo().with_context(
            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
        ).write({
            'price_origin': 'product_pricing',
            'price_origin_verified': True,
            'price_origin_evidence': 'product_pricing_apply',
        })
        self.assertTrue(
            pricing_line.with_user(self.pricing_user).can_edit_pricelist_discount
        )
        pricing_line.with_user(self.pricing_user).write({'discount': 45.0})
        self.assertEqual(pricing_line.discount, 45.0)

        manager_order = self._order(owner=self.sales_manager)
        manager_line = self._line(manager_order)
        manager_order.with_user(self.sales_manager).action_preview_product_pricing()
        manager_line.with_user(self.sales_manager).write({
            'price_unit': 88.0,
            'discount': 60.0,
        })
        self.assertEqual(manager_line.price_origin, 'edited')
        self.assertTrue(
            manager_line.with_user(self.sales_manager).can_edit_pricelist_discount
        )
        self.assertTrue(manager_line.price_origin_verified)
        self.assertEqual(manager_line.price_origin_evidence, 'manual_edit')

    def test_manager_can_certify_locked_historical_origin_without_changing_price(self):
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
        order.write({'state': 'sent'})

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
        with self.assertRaises(UserError):
            line.with_user(self.sales_manager).write({'name': 'Sent mutation'})

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
        self.assertTrue(
            root.xpath("//field[@name='quotation_item_number'][@optional='show']")
        )
        for action_name in (
            'action_preview_product_pricing',
            'action_apply_product_pricing',
        ):
            button = root.xpath("//button[@name=$name]", name=action_name)
            self.assertEqual(len(button), 1)
            self.assertTrue(button[0].get('help'))
    def test_assigned_salesperson_can_crud_draft_lines_but_unassigned_cannot(self):
        order = self.env['sale.order'].with_user(self.basic_user).create({
            'partner_id': self.partner.id,
            'user_id': self.basic_user.id,
        })
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
