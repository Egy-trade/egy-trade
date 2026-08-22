# -*- coding: utf-8 -*-
from odoo.addons.oit_contact_restriction.models.res_partner import (
    CRM_LEAD_CUSTOMER_CONTEXT_KEY,
)
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestContactCreateRestriction(TransactionCase):
    """Regression tests for res.partner.create restriction.

    Manual contact creation stays restricted to members of the Create Contact
    group, while the CRM lead-to-quotation conversion flow keeps creating
    customers for ordinary salespeople (upstream sale_crm tests
    TestLeadConvertToTicket.test_lead_convert_to_quotation_create /
    test_lead_convert_to_quotation_false_match_create).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.restricted_user = cls.env['res.users'].create({
            'name': 'Restricted Contact Creator',
            'login': 'oit_contact_restricted_creator',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('sales_team.group_sale_salesman').id,
            ])],
        })
        cls.allowed_user = cls.env['res.users'].create({
            'name': 'Allowed Contact Creator',
            'login': 'oit_contact_allowed_creator',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref(
                    'oit_contact_restriction.group_create_contact').id,
                # satisfy the standard res.partner create ACLs
                cls.env.ref('sales_team.group_sale_salesman').id,
            ])],
        })

    def _conversion_lead(self):
        return self.env['crm.lead'].sudo().create({
            'name': 'Conversion Lead',
            'contact_name': 'Amy Wong',
            'partner_name': 'Planet Express',
            'email_from': 'amy.wong@conversion.example.com',
            'user_id': self.restricted_user.id,
        }).with_user(self.restricted_user)

    def test_manual_create_denied_without_group(self):
        Partner = self.env['res.partner'].with_user(self.restricted_user)
        with self.assertRaises(ValidationError):
            Partner.create({'name': 'Manual Blocked Contact'})

    def test_manual_create_denied_in_batch_without_group(self):
        Partner = self.env['res.partner'].with_user(self.restricted_user)
        with self.assertRaises(ValidationError):
            Partner.create([
                {'name': 'Batch Blocked 1'},
                {'name': 'Batch Blocked 2'},
            ])

    def test_manual_create_allowed_with_group(self):
        Partner = self.env['res.partner'].with_user(self.allowed_user)
        partner = Partner.create({'name': 'Manual Allowed Contact'})
        self.assertTrue(partner.id)

    def test_forged_context_values_remain_denied(self):
        """RPC-supplied context values can never match the private token."""
        for forged in (True, False, 1, 'true', 'token'):
            with self.subTest(forged=forged):
                Partner = self.env['res.partner'].with_user(
                    self.restricted_user
                ).with_context(**{CRM_LEAD_CUSTOMER_CONTEXT_KEY: forged})
                with self.assertRaises(ValidationError):
                    Partner.create({'name': 'Forged Token Contact'})

    def test_crm_conversion_creates_customer_without_group(self):
        """Underlying conversion path used by the sale_crm quotation wizard.

        crm.quotation.partner.action_apply() calls exactly
        ``lead._handle_partner_assignment(create_missing=True)``; the module
        does not depend on sale_crm, so the test registry has no wizard and
        the underlying CRM path is exercised directly.
        """
        lead = self._conversion_lead()
        lead._handle_partner_assignment(create_missing=True)
        self.assertTrue(bool(lead.partner_id.id))
        self.assertEqual(lead.partner_id.name, 'Amy Wong')
