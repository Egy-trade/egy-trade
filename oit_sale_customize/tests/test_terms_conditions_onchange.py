# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.tests.common import SavepointCase


class TestTermsConditionsOnchange(SavepointCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref('base.res_partner_1')
        cls.terms = cls.env['terms.conditions'].create({
            'basic_name': 'Onchange test terms',
            'name': 'Draft-only terms preview',
        })

    def _order(self):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'note': 'Persisted customer note',
        })

    def test_draft_onchange_previews_terms_without_write(self):
        virtual = self.env['sale.order'].new({
            'partner_id': self.partner.id,
            'terms_conditions_id': self.terms.id,
            'note': 'Existing draft note',
        })
        with patch.object(type(virtual), 'write', side_effect=AssertionError('onchange must not write')):
            virtual._onchange_terms_conditions_id()
        self.assertEqual(virtual.note, self.terms.name)

    def test_sent_form_onchange_does_not_persist_note(self):
        order = self._order()
        if 'issued_offer_attachment_id' in order._fields:
            from odoo.addons.sale_revision_history.models.sale_order import (
                _LIFECYCLE_INTERNAL_TOKEN,
            )
            order.with_context(
                _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
            ).write({'state': 'sent'})
        else:
            order.write({'state': 'sent'})
        virtual = self.env['sale.order'].new({
            'partner_id': order.partner_id.id,
            'state': 'sent',
            'terms_conditions_id': self.terms.id,
            'note': order.note,
        })
        with patch.object(type(virtual), 'write', side_effect=AssertionError('sent form onchange must not write')):
            virtual._onchange_terms_conditions_id()
        self.assertEqual(virtual.note, 'Persisted customer note')
        order.invalidate_cache(['note'])
        self.assertEqual(order.note, 'Persisted customer note')
