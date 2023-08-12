# -*- coding: utf-8 -*-
{
    'name': "Custom Create Purchase Order from Sale Order",

    'summary': """
    Custom Create Purchase Order from Sale Order
        """,

    'description': """
        Long description of module's purpose
    """,

    'author': "Abdullah/OIT-Solution",
    'website': "https://www.oit-solution.com",
    'category': "OIT Solutions/apps",
    'license': 'AGPL-3',
    'sequence': 1,
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale_purchase', 'purchase_stock'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],
}
