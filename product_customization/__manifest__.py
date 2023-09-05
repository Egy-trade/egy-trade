
{
    'name': 'Product Management',
    'summary': 'Product Management',
    'author': "OIT Solutions",
    'company': 'OIT Solutions',
    'website': "http://www.oit-solution.com",
    'version': '15.0.0.1.0',
    'category': "OIT Solutions/apps",
    'license': 'AGPL-3',
    'sequence': 1,
    'depends': [
        'sale',
        'account',
        'sale_management',
        'web'
    ],
    'data': [
        'security/security.xml',
        'views/product_product_views.xml',
    ],
    'demo': [
        # 'demo/',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}

