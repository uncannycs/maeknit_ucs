from odoo import models, fields, api
import logging

SPEC_GARMENT_KEYWORDS = ('documentation', 'spec garment')

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    excalidraw_data = fields.Json(
        string="Excalidraw Sketch Data",
        related="production_id.bom_request_id.excalidraw_data",
        store=False,  
        readonly=False,
    )
    
    excalidraw_data_with_images = fields.Json(
        string='Excalidraw Data (Full)',
        related='production_id.excalidraw_data_with_images',
        store=False,
        readonly=True,
        help='Full excalidraw data with images restored from attachments for widget display'
    )

    garment_construction_data = fields.Json(
        string="Garment Construction Data",
        related="production_id.bom_request_id.garment_construction_data",
        store=False,
        readonly=False,
    )

    garment_construction_data_with_images = fields.Json(
        string='Garment Construction Data (Full)',
        related='production_id.garment_construction_data_with_images',
        store=False,
        readonly=True,
        help='Full garment construction data with images restored from attachments for widget display'
    )

    # NEW: Related Whole CAD
    whole_cad_data = fields.Json(
        string='Whole CAD Data',
        related='production_id.whole_cad_data',
        store=True,
        readonly=False,
    )
    
    whole_cad_data_with_images = fields.Json(
        string='Whole CAD Data (Full)',
        related='production_id.whole_cad_data_with_images',
        store=False,
        readonly=True,
        help='Full whole CAD data with image URL for widget display'
    )

    cad_pom_data = fields.Json(
        string='CAD & POM Data',
        related='production_id.cad_pom_data',
        store=True,
        readonly=False,
    )

    cad_pom_data_with_images = fields.Json(
        string='CAD & POM Data (Full)',
        related='production_id.cad_pom_data_with_images',
        store=False,
        readonly=True,
        help='Full CAD & POM data with image URL for widget display'
    )

    # NEW: Related Panel CAD
    measurement_widget_data = fields.Json(
        string='Panel CAD Data',
        related='production_id.measurement_widget_data',
        store=True,
        readonly=False,
    )

    measurement_widget_data_with_images = fields.Json(
        string='Panel CAD Data (Full)',
        related='production_id.measurement_widget_data_with_images',
        store=False,
        readonly=True,
    )

    # NEW: Related Calibration
    calibration_data = fields.Json(
        string='Calibration Data',
        related='production_id.calibration_data',
        store=True,
        readonly=False,
    )
    
    calibration_data_with_images = fields.Json(
        string='Calibration Data (Full)',
        related='production_id.calibration_data_with_images',
        store=False,
        readonly=True,
    )
    
    product_category = fields.Selection(
        related='production_id.product_category',
        store=True,
        readonly=True,
    )
    
    garment_doc_data = fields.Json(
        string="Garment Documentation",
        related='production_id.garment_doc_data',
        store=False,  
        readonly=False,
    )

    linking_dial_measurements = fields.Json(
        string='Linking Dial Measurements',
        related='production_id.linking_dial_measurements',
        store=False,  
        readonly=False,
    )

    is_knit_program = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    is_knit_operation = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    is_program_operation = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    is_documentation_operation = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    is_link_operation = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    is_loose_ends_operation = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    is_wash_operation = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    is_steam_operation = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    is_dry_operation = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    is_stitch_density_operation = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    is_stitch_construction_operation = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    is_garment_construction_operation = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    is_uk_company = fields.Boolean(
        related='production_id.is_uk_company',
        store=False,
    )
    is_development_bom = fields.Boolean(
        related='production_id.bom_request_id.is_development_bom',
        store=True,
        readonly=True,
    )
    
    is_production_bom = fields.Boolean(
        compute='_compute_is_production_bom',
        store=True,
        readonly=True,
    )
    
    is_grading_bom = fields.Boolean(
        related='production_id.bom_request_id.is_grading_bom',
        store=True,
        readonly=True,
    )
    show_stitch_density_tab = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    show_panel_cad_tab = fields.Boolean(
        compute='_compute_flags',
        store=False,
        help='True if product category is panel'
    )
    show_whole_cad_tab = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    show_sketch_tab = fields.Boolean(
        compute='_compute_flags',
        store=False,        
    )
    show_garment_construction_tab = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    show_linking_dial_tab = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    show_swatch_documentation_tab = fields.Boolean(
        compute='_compute_flags',
        store=False,        
    )
    show_garment_documentation_tab = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    show_cad_pom_tab = fields.Boolean(
        compute='_compute_flags',
        store=False,
    )
    
    comp_move_raw_ids = fields.One2many(
        'stock.move',
        related='production_id.move_raw_ids',
        readonly=False,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Partner",
        related="production_id.partner_id",
        store=True,
        readonly=True,
    )
    production_rel_service = fields.Many2one(
        'product.product',
        string='Service',
        related='production_id.rel_service',
        store=True,
        readonly=True,
    )
    
    @api.depends(
        'production_id',
        'production_id.bom_request_id',
        'production_id.bom_request_id.is_development_bom',
        'production_id.bom_request_id.is_grading_bom',
    )
    def _compute_is_production_bom(self):
        for wo in self:
            bom_req = wo.production_id.bom_request_id if wo.production_id else False

            # If no bom request -> production
            if not bom_req:
                wo.is_production_bom = True
                continue

            # If bom request exists -> production only when not dev and not grading
            wo.is_production_bom = not (bom_req.is_development_bom or bom_req.is_grading_bom or bom_req.is_swatch_bom)
    
    @api.depends('operation_id', 'operation_id.name')
    def _compute_flags(self):
        for wo in self:
            operation_name = (wo.operation_id.name or wo.name or '').lower()

            wo.is_knit_program = 'knit' in operation_name or 'program' in operation_name
            wo.is_knit_operation = 'knit' in operation_name
            wo.is_program_operation = 'program' in operation_name
            is_spec_garment_operation = any(keyword in operation_name for keyword in SPEC_GARMENT_KEYWORDS)
            wo.is_documentation_operation = is_spec_garment_operation
            wo.is_link_operation = 'link' in operation_name
            wo.is_loose_ends_operation = 'loose ends' in operation_name
            wo.is_wash_operation = 'wash' in operation_name
            wo.is_dry_operation = 'dry' in operation_name
            wo.is_steam_operation = 'steam' in operation_name
            wo.is_stitch_density_operation = 'stitch density' in operation_name
            wo.is_stitch_construction_operation = 'stitch construction' in operation_name
            wo.is_garment_construction_operation = 'garment construction' in operation_name
            
            # SAFE RELATIONS
            bom_req = wo.production_id.bom_request_id if wo.production_id else False
            is_development_bom = bom_req.is_development_bom if bom_req else False
            is_grading_bom = bom_req.is_grading_bom if bom_req else False
            is_production_bom = wo.is_production_bom if wo.is_production_bom else False

            # ALWAYS ASSIGN ALL FIELDS
            wo.show_panel_cad_tab = (
                wo.product_category == 'garment'
                and (is_development_bom or is_grading_bom or is_production_bom)
                and (wo.is_knit_operation or wo.is_program_operation or wo.is_link_operation)
            )

            wo.show_whole_cad_tab = (
                wo.product_category == 'garment'
                and (is_development_bom or is_grading_bom or is_production_bom)
                and (wo.is_knit_operation or wo.is_program_operation or wo.is_link_operation)
            )

            wo.show_sketch_tab = (
                (wo.product_category == 'swatch' and (wo.is_knit_operation or wo.is_program_operation))
                or (wo.product_category == 'garment' and (is_development_bom or is_grading_bom or is_production_bom) and (wo.is_knit_operation or wo.is_program_operation))
                or wo.is_stitch_construction_operation
            )

            wo.show_garment_construction_tab = wo.is_garment_construction_operation

            wo.show_stitch_density_tab = (
                (wo.product_category == 'swatch' and (wo.is_knit_operation or wo.is_program_operation or wo.is_stitch_density_operation))
                or (wo.product_category == 'garment' and (is_development_bom or is_grading_bom or is_production_bom) and (wo.is_knit_operation or wo.is_program_operation))
            )

            wo.show_linking_dial_tab = (
                wo.product_category == 'garment'
                and (is_development_bom or is_grading_bom or is_production_bom)
                and wo.is_link_operation
            )

            wo.show_swatch_documentation_tab = (
                wo.product_category == 'swatch'
                and (wo.is_documentation_operation or wo.is_knit_operation or wo.is_program_operation)
            )

            wo.show_garment_documentation_tab = (
                wo.product_category == 'garment'
                and (is_development_bom or is_grading_bom or is_production_bom)
                and (wo.is_documentation_operation or wo.is_knit_operation or wo.is_program_operation)
            )

            wo.show_cad_pom_tab = 'cad' in operation_name and 'pom' in operation_name
