# -*- coding: utf-8 -*-
import ast
from pathlib import Path

from odoo.tests import TransactionCase

MODULE_DIR = Path(__file__).resolve().parents[1]


def _destructive_m2m_commands(path):
    """Return True when ``path`` contains an executable Many2many command
    tuple starting with ``2`` inside a list literal.

    AST-based on purpose: command ``(2, id)`` deletes the comodel record
    itself, while ``(3, id)`` only unlinks membership. Comments and
    docstrings are never parsed as AST nodes, so mentioning the forbidden
    tuple there cannot trigger a false positive.
    """
    tree = ast.parse(path.read_text(encoding='utf-8'), str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.List):
            for element in node.elts:
                if (isinstance(element, ast.Tuple) and element.elts
                        and isinstance(element.elts[0], ast.Constant)
                        and element.elts[0].value == 2):
                    return True
    return False


class TestCompanyLgGroupToggle(TransactionCase):
    """Regression tests for the use_lg group toggle on res.company.

    Disabling LG accounting used to write ``[(2, user_id)]`` on
    res.groups.users; command (2, id) DELETES the comodel record itself, so
    creating/using a company raised "You can not remove the admin user" while
    base form tests created companies. It must use (3, id): unlink the
    membership only.
    """

    def test_company_creation_never_deletes_users(self):
        company = self.env['res.company'].create({'name': 'LG Toggle Co'})
        self.assertTrue(company.id)
        self.assertTrue(self.env.ref('base.user_admin').exists())
        self.assertTrue(self.env.ref('base.user_root').exists())

    def test_no_destructive_m2m_command_in_module_models(self):
        offenders = [
            path.name for path in sorted((MODULE_DIR / 'models').glob('*.py'))
            if _destructive_m2m_commands(path)
        ]
        self.assertEqual(
            offenders, [],
            'command (2, id) deletes comodel records; membership updates on '
            'res.groups.users must use (3, id) instead',
        )
