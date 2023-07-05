# -*- coding: utf-8 -*-
{
    'name': "currency_rate_sale_order",

    'summary': """
    Currency Rate live in Sale Order
       """,

    'description': """
        Long description of module's purpose
    """,

    'author': "Abdullah/OIT-Solution",
    'website': "https://www.oit-solution.com",
    'category': "OIT Solutions/apps",
    'license': 'AGPL-3',
    'sequence': 1,

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale'],

    # always loaded
    'data': [
        'views/sale_order.xml',
    ],

}
