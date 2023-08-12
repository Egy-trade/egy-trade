# -*- coding: utf-8 -*-
{
    'name': "Custom Sale Order Report",

    'summary': """
        Custom Sale Order Report""",

    'description': """
        Long description of module's purpose
    """,

    'author': "Abdullah/Oit-solution",
    'website': "https://www.oit-solution.com",

    'category': 'Sales',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
        'report/sale_report_template.xml',
    ],

}
