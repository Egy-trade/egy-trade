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

    @classmethod
    def tearDownClass(cls):
        cls.company.write({
            'quotation_vat_tax_id': cls.old_taxes[0].id,
            'quotation_retention_tax_id': cls.old_taxes[1].id,
            'quotation_withholding_responsible_id': cls.old_taxes[2].id,
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
        evidence = order.withholding_evidence_ids
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence.tax_id, self.withholding)
        self.assertAlmostEqual(evidence.expected_amount, 1.0)
        self.assertTrue(evidence.activity_id)

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

    def test_expiry_override_is_still_a_finance_requirement(self):
        order = self._order()
        target_days = order.company_id.quotation_expiry_days_default + 1
        with self.assertRaises(ValidationError):
            order.write({'offer_expiry_days': target_days})
        order.write({
            'offer_expiry_days': target_days,
            'finance_approval_reason': 'Client tender requires longer validity.',
        })
        self.assertIn('validity_override', order._finance_requirement_codes())

    def test_high_value_is_still_a_finance_requirement(self):
        eur = self.env.ref('base.EUR')
        pricelist = self.env['product.pricelist'].create({
            'name': 'Quotation finance high value test', 'currency_id': eur.id,
        })
        order = self._order(pricelist_id=pricelist.id)
        line = self._line(order)
        line.write({'price_unit': 100000.0})
        self.assertIn('high_value', order._finance_requirement_codes())

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
        order.write({'state': 'sent'})
        with self.assertRaises(UserError):
            order.action_approve_finance_requirements()

    def test_closed_evidence_details_are_immutable(self):
        order = self._order(apply_withholding=True)
        self._line(order)
        order._create_pending_withholding_evidence()
        evidence = order.withholding_evidence_ids
        evidence.with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({
            'status': 'received',
        })
        with self.assertRaises(AccessError):
            evidence.write({'remittance_reference': 'rewritten'})
