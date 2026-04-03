# -*- coding: utf-8 -*-
{
    'name': 'Maeknit DHL Integration (RFQ/PO)',
    'version': '18.0.1.10.0',
    'category': 'Purchase',
    'summary': 'Maeknit: Automatic Shipping (DHL) and Duty/Tax estimates for RFQs/POs',
    'author': 'Maeknit',
    'depends': ['purchase', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/product_hs_code_wizard_views.xml',
        'views/product_template_views.xml',
        'views/purchase_order_views.xml',
        'views/res_company_views.xml',
        'views/purchase_order_reports.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'maeknit_dhl_integration/static/src/css/style.css',
        ],
},
    'installable': True,
    'license': 'LGPL-3',
}
