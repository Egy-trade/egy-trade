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
    'version': '16.0.2.9.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale', 'sale_management', 'account', 'egy-trade_custom', 'universal_discount', 'sale_stock', 'sale_discount_total'],

    # always loaded
    'data': [
        'security/res_groups.xml',
        'security/finance_controls_security.xml',
        'security/role_visibility.xml',
        'security/ir.model.access.csv',
        'views/product_pricing_preview.xml',
        'views/sale_order.xml',
        'views/offer_expiry.xml',
        'views/product_analysis.xml',
        'views/role_visibility.xml',
        'views/finance_controls.xml',
    ],

}
