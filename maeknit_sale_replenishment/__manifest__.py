{
    'name': 'Maeknit Replenishment',
    'version': '18.0.0.6.0',
    'summary': 'Replenishment / Procurement Planning Screen linked to Sales Orders',
    'description': """
        Provides a BOM-like exploded view for procurement planning directly from Sales Orders.
        Features:
        - Explode BOMs from SO lines into a flat component list.
        - Edit quantities, routes, and lead times without changing the original BOM.
        - Create and update RFQs directly from the replenishment plan.
    """,
    'category': 'Inventory/Purchase',
    'author': 'Mahimul Islam (Maeknit)',
    'website': 'https://maeknit.io',
    'depends': ['sale', 'mrp', 'purchase', 'stock', 'sale_mrp'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/maeknit_replenishment_product_views.xml',
        'views/sale_order_views.xml',

    ],
    'assets': {
        'web.assets_backend': [
            'maeknit_sale_replenishment/static/src/components/replenishment_overview/maeknit_replenishment_overview.js',
            'maeknit_sale_replenishment/static/src/components/replenishment_overview/maeknit_replenishment_overview.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
