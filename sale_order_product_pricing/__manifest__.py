# -*- coding: utf-8 -*-
{
    'name': "product pricing in sale order",

    'summary': """
        product pricing in sale order
        """,

    'description': """
        Long description of module's purpose
    """,

    'author': "Abdullah/OIT-Solution",
    'website': "https://www.oit-solution.com",
    'category': 'Sales',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/res_groups.xml',
        'views/sale_order.xml',
        'views/product_analysis.xml',
    ],

}
