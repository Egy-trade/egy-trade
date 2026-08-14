# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import SavepointCase

from ..models.finance_controls import _FINANCE_INTERNAL_TOKEN


class TestQuotationTaxSelection(SavepointCase):
    """The tax selector is a sales document aid, not accounting automation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env.ref('base.res_partner_1')
        cls.product = cls.env['product.product'].create({
            'name': 'Quotation tax selector test product', 'sale_ok': True, 'list_price': 100.0,
        })
        cls.vat = cls.env['account.tax'].create({
            'name': 'Quotation selector VAT 14', 'amount_type': 'percent', 'amount': 14.0,
            'type_tax_use': 'sale', 'company_id': cls.company.id,
        })
        cls.withholding = cls.env['account.tax'].create({
            'name': 'Quotation selector withholding 1', 'amount_type': 'percent', 'amount': -1.0,
            'type_tax_use': 'sale', 'company_id': cls.company.id,
        })
        cls.old_taxes = (
            cls.company.quotation_vat_tax_id,
            cls.company.quotation_retention_tax_id,
            cls.company.quotation_withholding_responsible_id,
            cls.company.quotation_high_value_threshold,
            cls.company.quotation_high_value_approver_group_id,
        )
        cls.company.write({
            'quotation_vat_tax_id': cls.vat.id,
            'quotation_retention_tax_id': cls.withholding.id,
            'quotation_withholding_responsible_id': cls.env.user.id,
        })
        cls.employee = cls.env['res.users'].create({
            'name': 'Quotation tax unauthorized employee',
            'login': 'quotation.tax.employee@example.test',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.qs = cls.env['res.users'].create({
            'name': 'Quotation Specialist approval test',
            'login': 'quotation.qs.approval@example.test',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('sales_team.group_sale_salesman').id,
                cls.env.ref('sale_order_product_pricing.quotation_specialist_group').id,
            ])],
        })
        cls.manager = cls.env['res.users'].create({
            'name': 'Quotation Manager approval test',
            'login': 'quotation.manager.approval@example.test',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('sale_order_product_pricing.quotation_manager_group').id,
            ])],
        })
        cls.high_value_group = cls.env['res.groups'].create({
            'name': 'High Value Approver test group',
            'category_id': cls.env.ref('base.module_category_sales_sales').id,
        })
        cls.high_value_user = cls.env['res.users'].create({
            'name': 'High Value approver test',
            'login': 'quotation.high.value@example.test',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('sales_team.group_sale_salesman').id,
                cls.high_value_group.id,
            ])],
        })

    @classmethod
    def tearDownClass(cls):
        cls.company.write({
            'quotation_vat_tax_id': cls.old_taxes[0].id,
            'quotation_retention_tax_id': cls.old_taxes[1].id,
            'quotation_withholding_responsible_id': cls.old_taxes[2].id,
            'quotation_high_value_threshold': cls.old_taxes[3],
            'quotation_high_value_approver_group_id': cls.old_taxes[4].id,
        })
        super().tearDownClass()

    def _order(self, **values):
        vals = {'partner_id': self.partner.id}
        vals.update(values)
        order = self.env['sale.order'].create(vals)
        return order

    def _line(self, order):
        if 'commercial_change_date' in order._fields:
            order.with_user(order.user_id)._record_commercial_change('update_today')
        return self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': self.product.id,
            'name': self.product.name, 'product_uom_qty': 1.0, 'price_unit': 100.0,
        })

    def test_default_is_vat_only_and_new_lines_follow_header(self):
        order = self._order()
        line = self._line(order)
        self.assertTrue(order.apply_vat)
        self.assertFalse(order.apply_withholding)
        self.assertEqual(line.tax_id, self.vat)

    def test_all_four_selections_apply_globally(self):
        scenarios = [
            (True, False, self.vat),
            (True, True, self.vat | self.withholding),
            (False, True, self.withholding),
            (False, False, self.env['account.tax']),
        ]
        for vat, withholding, expected in scenarios:
            order = self._order(
                apply_vat=vat, apply_withholding=withholding,
                vat_exemption_reason=False if vat else 'Customer exemption certificate pending',
            )
            line = self._line(order)
            self.assertEqual(line.tax_id, expected)

    def test_vat_exemption_requires_reason_and_manager_approval_before_issue(self):
        with self.assertRaises(ValidationError):
            self._order(apply_vat=False)
        order = self._order(apply_vat=False, vat_exemption_reason='VAT exempt customer')
        self._line(order)
        with self.assertRaises(UserError):
            order._check_finance_issue_requirements()
        order.action_approve_finance_requirements()
        self.assertTrue(order._check_finance_issue_requirements())

    def test_direct_line_tax_edits_are_rejected(self):
        order = self._order()
        line = self._line(order)
        with self.assertRaises(UserError):
            line.write({'tax_id': [(6, 0, [])]})

    def test_non_sales_user_cannot_change_header_tax_selection(self):
        order = self._order()
        with self.assertRaises(AccessError):
            order.with_user(self.employee).write({'apply_withholding': True})

    def test_withholding_evidence_is_created_only_when_selected(self):
        order = self._order(apply_withholding=True)
        self._line(order)
        order._create_pending_withholding_evidence()
        self.assertFalse(order.withholding_evidence_ids)

    def test_ambiguous_migrated_tax_selection_blocks_issue(self):
        order = self._order()
        self._line(order)
        order.with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({
            'tax_selection_review_required': True,
        })
        with self.assertRaises(UserError):
            order._check_finance_issue_requirements()

    def test_retention_only_approval_copy_needs_private_token(self):
        source = self._order()
        target = self._order()
        with self.assertRaises(AccessError):
            target._carry_retention_only_approvals_from(source)

    def test_withholding_change_keeps_existing_approval(self):
        order = self._order(apply_vat=False, vat_exemption_reason='Exempt tender')
        self._line(order)
        order.action_approve_finance_requirements()
        approval = order.finance_approval_ids.filtered(lambda item: item.code == 'vat_exemption')
        order.write({'apply_withholding': True})
        self.assertFalse(approval.invalidated)
        self.assertTrue(order._check_finance_issue_requirements())

    def test_reason_only_vat_exemption_clear_is_rejected(self):
        order = self._order(apply_vat=False, vat_exemption_reason='Exempt tender')
        with self.assertRaises(ValidationError):
            order.write({'vat_exemption_reason': False})

    def test_expiry_override_is_not_an_approval_requirement(self):
        order = self._order()
        target_days = order.company_id.quotation_expiry_days_default + 1
        order.write({'offer_expiry_days': target_days})
        self.assertNotIn('validity_override', order._quotation_issue_requirement_codes())

    def test_high_value_is_configured_and_includes_the_boundary(self):
        self.company.write({
            'quotation_high_value_threshold': 100.0,
            'quotation_high_value_approver_group_id': self.high_value_group.id,
        })
        order = self._order(user_id=self.high_value_user.id)
        self._line(order).write({'price_unit': 100.0})
        self.assertIn('high_value', order._quotation_issue_requirement_codes())
        self.company.write({
            'quotation_high_value_threshold': 0.0,
            'quotation_high_value_approver_group_id': False,
        })

    def test_manager_approves_qs_and_vat_off_from_one_snapshot(self):
        order = self._order(
            quotation_specialist_id=self.qs.id,
            apply_vat=False,
            vat_exemption_reason='Customer supplied an exemption certificate.',
        )
        self._line(order)
        with self.assertRaises(UserError):
            order._check_quotation_issue_approval_requirements()
        self.assertFalse(
            order.with_user(self.employee).can_approve_quotation_requirements
        )
        self.assertTrue(
            order.with_user(self.manager).can_approve_quotation_requirements
        )
        order.with_user(self.manager).action_approve_quotation_requirements()
        approvals = order.finance_approval_ids.filtered(lambda approval: not approval.invalidated)
        self.assertEqual(set(approvals.mapped('code')), {'quotation_manager', 'vat_exemption'})
        self.assertTrue(all(approval.snapshot_fingerprint for approval in approvals))
        self.assertTrue(order._check_quotation_issue_approval_requirements())

    def test_manager_cannot_approve_high_value_but_configured_user_can(self):
        self.company.write({
            'quotation_high_value_threshold': 100.0,
            'quotation_high_value_approver_group_id': self.high_value_group.id,
        })
        order = self._order(user_id=self.high_value_user.id)
        self._line(order).write({'price_unit': 100.0})
        with self.assertRaises(AccessError):
            order.with_user(self.manager).action_approve_quotation_requirements()
        self.assertFalse(
            order.with_user(self.manager).can_approve_quotation_requirements
        )
        self.assertTrue(
            order.with_user(self.high_value_user).can_approve_quotation_requirements
        )
        order.with_user(self.high_value_user).action_approve_quotation_requirements()
        self.assertEqual(
            order.finance_approval_ids.filtered(lambda approval: not approval.invalidated).mapped('code'),
            ['high_value'],
        )
        self.assertTrue(order._check_quotation_issue_approval_requirements())
        self.company.write({
            'quotation_high_value_threshold': 0.0,
            'quotation_high_value_approver_group_id': False,
        })

    def test_high_value_uses_company_currency_at_quotation_date(self):
        eur = self.env.ref('base.EUR')
        pricelist = self.env['product.pricelist'].create({
            'name': 'Quotation normalized high value test', 'currency_id': eur.id,
        })
        order = self._order(pricelist_id=pricelist.id)
        self._line(order).write({'price_unit': 101.0})
        converted = order._high_value_amount_company_currency()
        self.company.write({'quotation_high_value_threshold': converted})
        self.assertTrue(order._is_high_value_quotation())
        self.company.write({'quotation_high_value_threshold': 0.0})

    def test_legacy_state_actions_cannot_bypass_standard_workflow(self):
        order = self._order()
        states = dict(self.env['sale.order']._fields['state'].selection)
        self.assertNotIn('approve', states)
        self.assertNotIn('waiting', states)
        self.assertNotIn('waiting_approve', states)
        with self.assertRaises(UserError):
            order.action_to_approve()
        with self.assertRaises(UserError):
            order.action_approve()

    def test_direct_approval_record_creation_cannot_forge_approval(self):
        order = self._order()
        with self.assertRaises(AccessError):
            self.env['sale.order.finance.approval'].create({
                'order_id': order.id,
                'code': 'high_value',
                'label': 'Forged',
                'approver_id': self.env.user.id,
                'reason': 'Forged through RPC',
                'snapshot_fingerprint': 'forged',
            })

    def test_ordinary_employee_cannot_read_approval_audit_rows(self):
        order = self._order()
        self.env['sale.order.finance.approval'].with_context(
            _finance_internal_token=_FINANCE_INTERNAL_TOKEN,
        ).create({
            'order_id': order.id,
            'code': 'quotation_manager',
            'label': 'Test evidence',
            'approver_id': self.env.user.id,
            'reason': 'Test evidence only',
            'snapshot_fingerprint': order._quotation_approval_snapshot(),
        })
        with self.assertRaises(AccessError):
            self.env['sale.order.finance.approval'].with_user(self.employee).search([])

    def test_ordinary_user_cannot_approve_quotation_requirements(self):
        order = self._order(apply_vat=False, vat_exemption_reason='Exempt client')
        self._line(order)
        with self.assertRaises(AccessError):
            order.with_user(self.employee).action_approve_quotation_requirements()

    def test_commercial_quantity_change_invalidates_existing_approval(self):
        order = self._order(apply_vat=False, vat_exemption_reason='Exempt client')
        line = self._line(order)
        order.action_approve_finance_requirements()
        approval = order.finance_approval_ids.filtered(
            lambda item: item.code == 'vat_exemption'
        )
        self.assertTrue(approval)
        line.write({'product_uom_qty': 2.0})
        self.assertTrue(approval.invalidated)

    def test_approval_is_rejected_outside_draft(self):
        order = self._order(apply_vat=False, vat_exemption_reason='Exempt client')
        if 'issued_offer_attachment_id' in order._fields:
            from odoo.addons.sale_revision_history.models.sale_order import (
                _LIFECYCLE_INTERNAL_TOKEN,
            )
            order.with_context(
                _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
            ).write({'state': 'sent'})
        else:
            order.write({'state': 'sent'})
        with self.assertRaises(UserError):
            order.action_approve_finance_requirements()

    def test_withholding_does_not_create_quote_side_evidence_on_confirmation_path(self):
        order = self._order(apply_withholding=True)
        self._line(order)
        order._create_pending_withholding_evidence()
        self.assertFalse(order.withholding_evidence_ids)
