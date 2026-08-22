# -*- coding: utf-8 -*-
import ast
import re
from pathlib import Path

from odoo.tests import TransactionCase

MODULE_DIR = Path(__file__).resolve().parents[1]


def _render(node):
    """Render a domain leaf part as a comparable value."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return '.'.join(reversed(parts))
    return '<expr:%s>' % type(node).__name__


class TestCrmPartnerDomainCurrentUser(TransactionCase):
    """Regression tests for the crm.lead.partner_id restriction domain.

    The selectable-customer domain of ``crm.lead.partner_id`` must restrict
    partners to those whose ``allowed_users_ids`` contains the CURRENT user,
    expressed with the Odoo 16 domain free variable ``uid`` (the repository's
    established convention for Many2many membership domains).

    Referencing a record field such as ``user_id`` inside this model-level
    domain makes every view that shows ``partner_id`` without an overriding
    domain fail ir.ui.view validation whenever the matching ``user_id`` field
    node is hidden behind narrower groups (the CRM opportunity tree view
    restricts it to sales_team.group_sale_manager), aborting registry
    initialization with odoo.tools.convert.ParseError.
    """

    def _allowed_users_domain_strings(self):
        """Every string literal in the module source that looks like a domain
        on the partner allow-list."""
        source_path = MODULE_DIR / 'models' / 'models.py'
        found = []
        for node in ast.walk(ast.parse(source_path.read_text(encoding='utf-8'),
                                       str(source_path))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value.strip()
                if value.startswith('[') and 'allowed_users_ids' in value:
                    found.append(value)
        return found

    def _domain_leaves(self, domain_string):
        """Structural leaves of a domain string, e.g.
        ('allowed_users_ids', 'in', 'uid')."""
        tree = ast.parse(domain_string, mode='eval')
        assert isinstance(tree.body, ast.List), 'domain must be a list'
        leaves = []
        for element in tree.body.elts:
            leaves.append(tuple(_render(part) for part in element.elts))
        return leaves

    def test_partner_id_domain_is_current_user_uid_membership(self):
        domains = self._allowed_users_domain_strings()
        self.assertEqual(
            len(domains), 1,
            'exactly one allowed_users_ids domain is expected in '
            'partner_restriction/models/models.py, got: %r' % (domains,),
        )
        self.assertEqual(
            self._domain_leaves(domains[0]),
            [('allowed_users_ids', 'in', 'uid')],
            "the customer domain must be exactly the current-user membership "
            "filter [('allowed_users_ids', 'in', uid)] using the uid free "
            'variable',
        )

    def test_partner_id_domain_references_no_record_or_user_object(self):
        for domain_string in self._allowed_users_domain_strings():
            self.assertIsNone(
                re.search(r'\buser_id\b', domain_string),
                "domain %r must not reference the record field user_id: "
                "view validation rejects restricted-field references and "
                "the filter must apply to the current user instead" % domain_string,
            )
            self.assertIsNone(
                re.search(r'\buser\s*\.\s*id\b', domain_string),
                "domain %r must not use the user.id form: only the uid free "
                'variable is guaranteed by Odoo 16 domain evaluation and is '
                'this repository\u2019s working convention' % domain_string,
            )
            self.assertNotIn(
                "'ilike'", domain_string.lower(),
                "membership in allowed_users_ids must use 'in'; ilike against "
                "a many2many degrades to display-name substring matching",
            )
