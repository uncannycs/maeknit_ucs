# -*- coding: utf-8 -*-
{
    'name': 'Maeknit Vendor Bidding Integration',
    'version': '18.0.1.2.0',
    'category': 'Sales',
    'summary': 'Extends Sales Order to support a full vendor bidding workflow for garment manufacturing.',
    'description': "Manage sending bids to factories, receiving pricing, comparing landed costs, and confirming a winner.",
    'author': 'Maeknit',
    'depends': [
        'sale',
        'purchase',
        'maeknit_dhl_integration',
        'maeknit_sale_replenishment',
        'maeknit_contact_customization'
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/request_bids_wizard_views.xml',
        'wizard/shipping_duty_wizard_views.xml',
        'views/purchase_order_kanban_views.xml',
        'views/purchase_order_views.xml',
        'views/sale_order_views.xml',
        # 'views/res_partner_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
