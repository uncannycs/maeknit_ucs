{
    'name': 'Maeknit Excalidraw Integration',
    'version': '1.0',
    'description': 'MAEKNIT Excalidraw Integration',
    'summary': 'MAEKNIT Excalidraw Integration',
    'author': 'Maeknit',
    'depends': [ 'web', 'bus', 'base', 'mrp', 'mrp_workorder', 'stock', 'maeknit_sales_customization', 'maeknit_mfg_customization' ],
    'data': [
        'security/ir.model.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'maeknit_excalidraw/static/src/css/excalidraw_overrides.css',
            'maeknit_excalidraw/static/src/css/excalidraw_comments.css',
            'maeknit_excalidraw/static/src/js/excalidraw_comments.js',
            'maeknit_excalidraw/static/src/js/excalidraw_widget.js',
            'maeknit_excalidraw/static/src/xml/excalidraw_widget.xml',
        ],
    },
    'license': 'LGPL-3',
}
