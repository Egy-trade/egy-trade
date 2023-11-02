
{
    'name': 'OIT Sale Access',
    'summary': 'OIT Sale Access',
    'author': "OIT Solutions",
    'company': 'OIT Solutions',
    'website': "http://www.oit-solution.com",
    'version': '16.0.0.1.0',
    'category': "OIT Solutions/apps",
    'license': 'AGPL-3',
    'sequence': 1,
    'depends': [
        'base',
        'sale',
        'oit_sale_customize',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        # 'report/',
        # 'wizard/',
        'views/menu.xml',
        # 'data/',
    ],
    'demo': [
        # 'demo/',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}

