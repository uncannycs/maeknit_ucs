{
    'name': 'Maeknit BOM–MFG Bridge',
    'version': '1.1',
    'depends': [ 'web', 'base', 'mrp', 'mrp_workorder', 'stock', 'maeknit_sales_customization', 'maeknit_mfg_customization' ],
    'data': ['security/ir.model.access.csv', 'views/mrp_production_views.xml', 'views/mrp_workorder_views.xml', 'wizard/sync_from_mo_wizard_views.xml'],
    'assets': {
        'web.assets_backend': [
            'maeknit_bom_mfg_link/static/src/js/garment_doc_widget.js',
            'maeknit_bom_mfg_link/static/src/xml/garment_doc_widget.xml',
            'maeknit_bom_mfg_link/static/src/js/linking_dial_widget.js',
            'maeknit_bom_mfg_link/static/src/xml/linking_dial_widget.xml',
            'maeknit_bom_mfg_link/static/src/js/structure_list_enter_save.js',
            'maeknit_bom_mfg_link/static/src/js/mrp_uk_tab_highlight.js',
            'maeknit_bom_mfg_link/static/src/css/mrp_uk_tab_highlight.css',
            'maeknit_bom_mfg_link/static/src/js/stitch_density_panel.js',
            'maeknit_bom_mfg_link/static/src/xml/stitch_density_panel.xml',
        ],
    },
    'author': 'Maeknit',
    'license': 'LGPL-3',
}
