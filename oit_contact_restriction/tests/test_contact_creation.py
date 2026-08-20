from odoo.exceptions import ValidationError
from odoo.tests.common import SavepointCase


class ContactCreationCase(SavepointCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.salesperson = cls.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': 'Restricted CRM Salesperson',
            'login': 'restricted_crm_salesperson',
            'email': 'restricted.crm.salesperson@example.com',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('sales_team.group_sale_salesman').id,
            ])],
        })

    def test_direct_contact_creation_stays_restricted(self):
        with self.assertRaises(ValidationError):
            self.env['res.partner'].with_user(self.salesperson).create({
                'name': 'Unauthorized Direct Contact',
            })

    def test_rpc_context_cannot_forge_crm_authorization(self):
        with self.assertRaises(ValidationError):
            self.env['res.partner'].with_user(self.salesperson).with_context(
                _crm_contact_create_token='forged',
            ).create({'name': 'Forged Contact'})

    def test_standard_crm_conversion_can_create_customer(self):
        lead = self.env['crm.lead'].with_user(self.salesperson).create({
            'name': 'Authorized CRM Conversion',
            'contact_name': 'CRM Contact',
            'email_from': 'crm.contact@example.com',
            'user_id': self.salesperson.id,
        })

        partner = lead._create_customer()

        self.assertTrue(partner.exists())
        self.assertEqual(partner.name, 'CRM Contact')
