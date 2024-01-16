# -*- coding: utf-8 -*-
{
    'name': 'Data Clear',
    'category': 'Extra Tools',
    'author': 'Dmmsys 124358678@qq.com ',
    'sequence': 1,
    'summary': """A powerful testing tool.Easily clear any odoo object data what you want. """,
    'website': 'www.bonainfo.com',
    'version': '1.0',   
    'description': """Business Testing Data Clear. You can define default model group list by yourself to help your work. """,
    'license': 'LGPL-3',
    'support': '124358678@qq.com, bower_guo@msn.com',
    'price': '0',
    'currency:': 'EUR',
    'images': ['static/description/Dataclear.png'],


    # any module necessary for this one to work correctly
    'depends': ['base'],

    # always loaded
    'data': [
        'data/clear_data.xml',
        'security/ir.model.access.csv',
        'views/clear_data_views.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        #'demo/demo.xml',
    ],
}
