from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from odoo.tools.translate import _
import logging
from markupsafe import Markup

class MrpBom(models.Model):
    _inherit = 'mrp.bom'
    
    is_development_bom = fields.Boolean(
    compute='_compute_bom_flags',
    store=True
    )
    is_garment_bom = fields.Boolean(
    compute="_compute_bom_flags",
    store=True
    )
    is_swatch_bom = fields.Boolean(
        compute="_compute_bom_flags",
        store=True
    )
    is_grading_bom = fields.Boolean(
        compute='_compute_bom_flags',
        store=True
    )
    is_reverse_bom = fields.Boolean(
        compute='_compute_bom_flags',
        store=True
    )   
    is_production_bom = fields.Boolean(
        compute='_compute_bom_flags',
        store=True
    )
    is_production_ready = fields.Boolean(
        store=True,
        default=False
    )
    rel_service = fields.Many2one(
        'product.product',
        string='Related Service',
    )    
    # Run, Colorway, Size fields for Garment
    run_id = fields.Many2one('product.attribute.value', string='Run', 
                            domain="[('attribute_id.name', '=', 'Run')]")
    style_colorway_ids = fields.Many2many('product.attribute.value',
                                         compute='_compute_style_colorway_ids',
                                         string='Available Colorways')
    style_size_ids = fields.Many2many('product.attribute.value',
                                      relation='mrp_bom_style_size_rel',
                                      compute='_compute_style_size_ids',
                                      string='Available Sizes')
    colorway_id = fields.Many2one('product.attribute.value', string='Colorway',
                                 domain="[('attribute_id.name', '=', 'Colorway')]")

    style_yarn_variant_ids = fields.Many2many('product.attribute.value', 
                                                compute='_compute_style_yarn_variant_ids', 
                                                string='Available Yarn Variants')
    yarn_variant = fields.Many2one('product.attribute.value', string='Yarn Variant', 
                                 domain="[('attribute_id.name', '=', 'Yarn Variant')]")
    
    def action_set_production_ready_status(self):
        self.write({'is_production_ready': True})
        return True
    
    @api.depends('product_tmpl_id', 'rel_service')
    def _compute_bom_flags(self):
        for bom in self:
            bom.is_garment_bom = False
            bom.is_swatch_bom = False
            bom.is_development_bom = False
            bom.is_grading_bom = False
            bom.is_reverse_bom = False
            bom.is_production_bom = False
            if ( bom.product_tmpl_id ):
                category = getattr(bom.product_tmpl_id, 'product_category', '').lower()
            else:
                category = 'garment'
            if category == 'garment':
                bom.is_garment_bom = True
            elif category == 'swatch':
                bom.is_swatch_bom = True

            if bom.rel_service:
                name = (bom.rel_service.name or '').lower()
                if 'development' in name:
                    bom.is_development_bom = True
                elif 'grading' in name:
                    bom.is_grading_bom = True
                elif 'production' in name:
                    bom.is_production_bom = True
                elif 'reverse' in name:
                    bom.is_reverse_bom = True
                elif 'swatch' in name:
                    bom.is_swatch_bom = True
                    
    is_uk_company = fields.Boolean(
    compute='_compute_is_uk_company',
    store=False,
    )
    @api.depends('company_id')
    def _compute_is_uk_company(self):
        for record in self:
            record.is_uk_company = 'uk' in (record.company_id.name or '').lower()
    @api.onchange('yarn_variant')
    def _onchange_yarn_variant(self):
        """Ensure style yarn variant exists when yarn variant is selected"""
        if self.yarn_variant and self.product_tmpl_id:
            self.env['style.yarn.variant'].get_or_create(self.product_tmpl_id.id, self.yarn_variant.id)
    
    @api.onchange('colorway_id')
    def _onchange_colorway_id_create(self):
        """Handle creation of new colorway values"""
        if self.colorway_id and not self.colorway_id.id and self.colorway_id.name:
            colorway_attr = self._get_colorway_attribute()
            if colorway_attr:
                new_colorway = self.env['product.attribute.value'].create({
                    'name': self.colorway_id.name,
                    'attribute_id': colorway_attr.id,
                })
                self.colorway_id = new_colorway
    
    size_id = fields.Many2one(
                    'product.attribute.value',
                    string='Size',
                    domain="[('attribute_id.name', '=', 'Size')]"
                )
    
    swatch_number_id = fields.Many2one('product.attribute.value', string='Swatch #', 
                                      domain="[('attribute_id.name', '=', 'Swatch #')]")
    
    style_colorway_id = fields.Many2one('style.colorway', string='Style Colorway',
                                       domain="[('product_tmpl_id', '=', product_tmpl_id)]")
    
    partner_id = fields.Many2one('res.partner', string='Customer')
    order_date = fields.Date(string='Order Date')
    due_date = fields.Date(string='Due Date')
    sample = fields.Char(
        string="Sample",
        compute='_compute_sample',
        store=True,
        readonly=True,
    )

    @api.depends('version')
    def _compute_sample(self):
        for bom in self:
            bom.sample = f"Sample {bom.version or 1}"
    revision = fields.Char(
        string="Revision",
    )
    
    body_stitch_id = fields.Many2one('stitch.library', string='Body Stitch', 
                                    domain="[('body_part', 'in', ['body', 'other'])]")
    cuff_stitch_id = fields.Many2one('stitch.library', string='Cuff Stitch',
                                    domain="[('body_part', 'in', ['cuff', 'other'])]")
    
    body_stitch = fields.Selection([
        ('jersey', 'Jersey'),
        ('interlock', 'Interlock'),
        ('rib', 'Rib'),
        ('2x1_rib', '2x1 Rib'),
        ('2x2_rib', '2x2 Rib'),
        ('other', 'Other')
    ], string='Legacy Body Stitch')
    
    cuff_stitch = fields.Selection([
        ('jersey', 'Jersey'),
        ('interlock', 'Interlock'),
        ('rib', 'Rib'),
        ('2x1_rib', '2x1 Rib'),
        ('2x2_rib', '2x2 Rib'),
        ('other', 'Other')
    ], string='Legacy Cuff Stitch')
    
    company_id = fields.Many2one(
        'res.company', 'Company', index=True,
        default=lambda self: self.env.company)
    machine_id = fields.Many2one('machine.library', string='Machine')

    machine_id_selection = fields.Selection(
        [
            ('shima', 'Shima'),
            ('stoll', 'Stoll'),
        ],
        default=lambda self: 'shima' if 'uk' in (self.env.company.name or '').lower() else 'stoll',
        string='Machine',
    )
    gauge_id = fields.Many2one('gauge.library', string='Gauge')
    machine_file = fields.Binary(string='Machine File', attachment=True)
    machine_filename = fields.Char(string='Machine Filename')
    expected_machine_time = fields.Char(string='Expected Machine Time')
    hs_code = fields.Char(string='HS Code', related='product_tmpl_id.hs_code', readonly=True)
    excalidraw_link = fields.Char(
        string='Excalidraw Link',
        help='Optional link to the Excalidraw diagram that documents this MO.',
    )
    # Cost calculation fields
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                 default=lambda self: self.env.company.currency_id.id)
    grading_price_unit = fields.Float(string='Grading Price Unit', help="Price per graded size for grading BOMs")

    @api.onchange('body_stitch_id')
    def _onchange_body_stitch_id(self):
        """Update legacy body_stitch field when body_stitch_id changes"""
        if self.body_stitch_id and self.body_stitch_id.stitch_type_selection:
            self.body_stitch = self.body_stitch_id.stitch_type_selection
        elif self.body_stitch_id and self.body_stitch_id.stitch_type:
            # Try to map the free text to the legacy selection field if possible
            stitch_type_lower = self.body_stitch_id.stitch_type.lower()
            if 'jersey' in stitch_type_lower:
                self.body_stitch = 'jersey'
            elif 'interlock' in stitch_type_lower:
                self.body_stitch = 'interlock'
            elif '2x1' in stitch_type_lower and 'rib' in stitch_type_lower:
                self.body_stitch = '2x1_rib'
            elif '2x2' in stitch_type_lower and 'rib' in stitch_type_lower:
                self.body_stitch = '2x2_rib'
            elif 'rib' in stitch_type_lower:
                self.body_stitch = 'rib'
            else:
                self.body_stitch = 'other'

    @api.onchange('cuff_stitch_id')
    def _onchange_cuff_stitch_id(self):
        """Update legacy cuff_stitch field when cuff_stitch_id changes"""
        if self.cuff_stitch_id and self.cuff_stitch_id.stitch_type_selection:
            self.cuff_stitch = self.cuff_stitch_id.stitch_type_selection
        elif self.cuff_stitch_id and self.cuff_stitch_id.stitch_type:
            # Try to map the free text to the legacy selection field if possible
            stitch_type_lower = self.cuff_stitch_id.stitch_type.lower()
            if 'jersey' in stitch_type_lower:
                self.cuff_stitch = 'jersey'
            elif 'interlock' in stitch_type_lower:
                self.cuff_stitch = 'interlock'
            elif '2x1' in stitch_type_lower and 'rib' in stitch_type_lower:
                self.cuff_stitch = '2x1_rib'
            elif '2x2' in stitch_type_lower and 'rib' in stitch_type_lower:
                self.cuff_stitch = '2x2_rib'
            elif 'rib' in stitch_type_lower:
                self.cuff_stitch = 'rib'
            else:
                self.cuff_stitch = 'other'


    @api.depends('bom_line_ids.product_id', 'bom_line_ids.product_qty', 'bom_line_ids.unit_cost', 'is_grading_bom', 'grading_price_unit')
    def _compute_total_cost(self):
        """Compute the total cost of the BOM based on component costs or grading price"""
        for bom in self:
            logging.info(f" Custom Code: Computing total cost for BOM {bom.id}")
            if bom.is_grading_bom:
                bom.total_cost = bom.grading_price_unit
                if bom.product_id: # This is the graded variant
                    bom.product_id.standard_price = bom.grading_price_unit
                    # Assuming 'cost_price' is a custom field on product.product
                    if hasattr(bom.product_id, 'cost_price'):
                        bom.product_id.cost_price = bom.grading_price_unit
            else:
                total = 0.0
                for line in bom.bom_line_ids:
                    if line.product_id and line.product_qty > 0:
                        # Assuming 'cost_price' is a custom field on product.product
                        component_cost = line.product_id.cost_price if hasattr(line.product_id, 'cost_price') else line.product_id.standard_price
                        line_cost = component_cost * line.product_qty
                        total += line_cost
                
                logging.info(f" Custom Code: Total cost for BOM {bom.id}: {total}")
                bom.total_cost = total
                
                # Update the product variant cost if this is a garment or swatch BOM
                if (bom.is_garment_bom or bom.is_swatch_bom) and bom.product_id: # Use bom.product_id (the variant)
                    bom.product_id.standard_price = total
                    # Assuming 'cost_price' is a custom field on product.product
                    if hasattr(bom.product_id, 'cost_price'):
                        bom.product_id.cost_price = total
        
    @api.onchange('product_tmpl_id')
    def _onchange_product_tmpl_id(self):
        self.colorway_id = False
        self.style_colorway_id = False

    
    @api.onchange('style_colorway_id')
    def _onchange_style_colorway_id(self):
        """Update colorway_id when style_colorway_id changes"""
        if self.style_colorway_id:
            self.colorway_id = self.style_colorway_id.colorway_id
        else:
            self.colorway_id = False
    
    @api.onchange('colorway_id')
    def _onchange_colorway_id(self):
        """Update or create style_colorway_id when colorway_id changes"""
        if self.colorway_id and self.product_tmpl_id:
            # Find existing style colorway
            style_colorway = self.env['style.colorway'].search([
                ('product_tmpl_id', '=', self.product_tmpl_id.id),
                ('colorway_id', '=', self.colorway_id.id)
            ], limit=1)
            
            if style_colorway:
                self.style_colorway_id = style_colorway
            else:
                # Create new style colorway automatically
                style_colorway = self.env['style.colorway'].create({
                    'product_tmpl_id': self.product_tmpl_id.id,
                    'colorway_id': self.colorway_id.id,
                    'created_by_bom': True
                })
                self.style_colorway_id = style_colorway
        elif not self.colorway_id:
            self.style_colorway_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            product_tmpl_id = vals.get('product_tmpl_id')
            colorway_id = vals.get('colorway_id')
            size_id = vals.get('size_id')
            yarn_variant = vals.get('yarn_variant')
            # colorway + size = Garment BOM
            # colorway + yarn_variant = Swatch BOM
            
            rel_service_id = vals.get('rel_service')

            rel_service = False
            if rel_service_id:
                rel_service = self.env['product.product'].browse(rel_service_id)

            # -----------------------------
            # GARMENT BOM LOGIC
            # -----------------------------
            if product_tmpl_id and colorway_id and size_id and rel_service_id:
                duplicate = self.search([
                    ('product_tmpl_id', '=', product_tmpl_id),
                    ('colorway_id', '=', colorway_id),
                    ('size_id', '=', size_id),
                    ('rel_service', '=', rel_service_id),
                ], limit=1)
                '''
                if duplicate:
                    raise UserError(
                        f"""
                        Duplicate Garment BOM exists.
                        Product: {duplicate.product_tmpl_id.name}
                        Colorway: {duplicate.colorway_id.name}
                        Size: {duplicate.size_id.name}
                        Service: {duplicate.rel_service.name}
                        ID: {duplicate.id}
                        """
                    )
                '''
            # -----------------------------
            # SWATCH LOGIC
            # -----------------------------
            if (
                product_tmpl_id
                and colorway_id
                and rel_service
                and 'swatch' in rel_service.product_tmpl_id.name.lower()
            ):
                if yarn_variant:
                    duplicate = self.search([
                        ('product_tmpl_id', '=', product_tmpl_id),
                        ('colorway_id', '=', colorway_id),
                        ('yarn_variant', '=', yarn_variant),
                        ('rel_service', '=', rel_service_id),
                    ], limit=1)
                else:
                    duplicate = self.search([
                        ('product_tmpl_id', '=', product_tmpl_id),
                        ('colorway_id', '=', colorway_id),
                        ('rel_service', '=', rel_service_id),
                    ], limit=1)

                if duplicate:
                    raise UserError(
                        f"""
                        Duplicate Swatch BOM exists.
                        Product: {duplicate.product_tmpl_id.name}
                        Colorway: {duplicate.colorway_id.name}
                        Yarn Variant: {duplicate.yarn_variant.name}
                        Service: {duplicate.rel_service.name}
                        ID: {duplicate.id}
                        """
                    )


        boms = super(MrpBom, self).create(vals_list)
        
        # Process each BOM to create variants if needed
        for bom in boms:
            if bom.colorway_id and bom.product_tmpl_id:
                style_colorway = self.env['style.colorway'].get_or_create_style_colorway(
                    bom.product_tmpl_id.id, bom.colorway_id.id
                )
                bom.style_colorway_id = style_colorway

            if bom.size_id and bom.product_tmpl_id:
                self.env['style.size'].get_or_create_style_size(
                    bom.product_tmpl_id.id, bom.size_id.id
                )

            if bom.yarn_variant and bom.product_tmpl_id:
                self.env['style.yarn.variant'].get_or_create(bom.product_tmpl_id.id, bom.yarn_variant.id)
                
            if bom.is_garment_bom and bom.colorway_id and bom.size_id and bom.product_tmpl_id: 
                self._ensure_attribute_values_exist(bom.product_tmpl_id, bom.colorway_id, bom.size_id)
                
                # Find or create only the specific variant for this BOM
                variant = self._find_or_create_specific_garment_variant(bom.product_tmpl_id, bom.colorway_id, bom.size_id)
                
                if variant and bom.product_id.id != variant.id:
                    bom.product_id = variant.id
                
                # Force recalculation of total cost
                bom._compute_total_cost()
                
                    
            elif bom.is_swatch_bom and bom.colorway_id and bom.product_tmpl_id:
                # Create attribute lines with single values for this BOM
                if bom.yarn_variant:
                    self._ensure_attribute_values_exist(bom.product_tmpl_id, bom.colorway_id, bom.yarn_variant)
                    variant = self._find_or_create_swatch_variant(
                        bom.product_tmpl_id,
                        bom.colorway_id,
                        bom.yarn_variant
                        )

                else:
                    self._ensure_attribute_values_exist(bom.product_tmpl_id, bom.colorway_id, None)
                    variant = self._find_or_create_swatch_variant(
                    bom.product_tmpl_id,
                    bom.colorway_id,
                    None
                )

                if variant and bom.product_id.id != variant.id:
                    bom.product_id = variant.id
                
                # Force recalculation of total cost
                bom._compute_total_cost()
                    
            elif bom.is_grading_bom and bom.size_id and bom.product_tmpl_id: 
                self._create_single_value_grading_attribute_lines(bom.product_tmpl_id, bom.size_id)
                if bom.colorway_id:
                    variant = self._find_or_create_specific_garment_variant(bom.product_tmpl_id, bom.colorway_id, bom.size_id)
                else:
                    variant = self._find_or_create_grading_variant(bom.product_tmpl_id, bom.size_id)
                if variant and bom.product_id.id != variant.id:
                    bom.product_id = variant.id
                bom._compute_total_cost() 
        
        return boms
    
    def write(self, vals):
        """Override write to automatically update product variants for garment/swatch BOMs"""
        res = super(MrpBom, self).write(vals)
        
        # Check if relevant fields were updated
        garment_fields = [ 'colorway_id', 'size_id', 'bom_line_ids']
        swatch_fields = ['yarn_variant', 'colorway_id', 'bom_line_ids']
        grading_fields = ['size_id', 'bom_line_ids', 'grading_price_unit'] # New: Grading fields

        for bom in self: # Iterate over self to ensure each BOM is processed
            if (bom.yarn_variant and bom.product_tmpl_id and
                ('yarn_variant' in vals or 'product_tmpl_id' in vals)):
                self.env['style.yarn.variant'].get_or_create(bom.product_tmpl_id.id, bom.yarn_variant.id)

            if (bom.size_id and bom.product_tmpl_id and
                ('size_id' in vals or 'product_tmpl_id' in vals)):
                self.env['style.size'].get_or_create_style_size(bom.product_tmpl_id.id, bom.size_id.id)

            if any(field in vals for field in garment_fields):
                if bom.is_garment_bom and bom.product_tmpl_id:
                    if bom.colorway_id and bom.size_id:
                        # Create attribute lines with single values for this BOM
                        self._ensure_attribute_values_exist(bom.product_tmpl_id, bom.colorway_id, bom.size_id)
                        
                        # Find or create the variant
                        variant = self._find_or_create_specific_garment_variant(bom.product_tmpl_id, bom.colorway_id, bom.size_id)
                        
                        if variant and bom.product_id.id != variant.id:
                            bom.product_id = variant.id
            
            if any(field in vals for field in swatch_fields):
                if bom.is_swatch_bom and bom.product_tmpl_id:
                    if not bom.colorway_id:
                        return
                    tmpl = bom.product_tmpl_id
                    colorway = bom.colorway_id
                    yarn_variant = bom.yarn_variant or False  
                    self._ensure_attribute_values_exist(tmpl, colorway, yarn_variant)
                    variant = self._find_or_create_swatch_variant(tmpl, colorway, yarn_variant)
                    if variant and bom.product_id.id != variant.id:
                        bom.product_id = variant.id
                    bom._compute_total_cost()
                        
            if any(field in vals for field in grading_fields): # New: Grading BOM update
                if bom.is_grading_bom and bom.product_tmpl_id:
                    if bom.size_id:
                        self._create_single_value_grading_attribute_lines(bom.product_tmpl_id, bom.size_id)
                        variant = self._find_or_create_grading_variant(bom.product_tmpl_id, bom.size_id)
                        if variant and bom.product_id.id != variant.id:
                            bom.product_id = variant.id
        return res
    
    def _create_single_value_grading_attribute_lines(self, product_tmpl, value_record):
        """
        Proper, safe variant expansion for Odoo 18.
        Adds the attribute value to the attribute line without removing others.
        """
        ProductAttributeLine = self.env['product.template.attribute.line']
        attr = value_record.attribute_id

        # 1. Look for existing attribute line
        existing_line = ProductAttributeLine.search([
            ('product_tmpl_id', '=', product_tmpl.id),
            ('attribute_id', '=', attr.id)
        ], limit=1)

        if existing_line:
            # Already exists → append value if missing
            if value_record.id not in existing_line.value_ids.ids:
                existing_line.write({'value_ids': [(4, value_record.id)]})
            return existing_line

        # 2. Create new attribute line (multi-value capable)
        return ProductAttributeLine.create({
            'product_tmpl_id': product_tmpl.id,
            'attribute_id': attr.id,
            'value_ids': [(4, value_record.id)],
        })


    def _find_or_create_grading_variant(self, product_tmpl, size_id):
        """New: Find or create a product variant with the given graded size attribute value"""
        ProductProduct = self.env['product.product']
        logging.info(f" Custom Code: Grading variant lookup for Product Template: {product_tmpl.name} (ID {product_tmpl.id}) and Size ID: {size_id.name} (ID {size_id.id})")

        # Ensure the attribute line exists on the product template
        self._create_single_value_grading_attribute_lines(product_tmpl, size_id)
        logging.info(" Custom Code:Ensured single-value grading attribute line exists on the template.")

        # Try to find a matching variant
        for variant in product_tmpl.product_variant_ids:
            variant_values = variant.product_template_attribute_value_ids.mapped('product_attribute_value_id')
            logging.info(f" Custom Code: Checking variant {variant.name} (ID {variant.id}) with attribute value IDs: {variant_values.ids}")
            if size_id.id in variant_values.ids:
                logging.info(f" Custom Code: Found existing variant {variant.name} (ID {variant.id}) for size {size_id.name}")
                return variant

        logging.info(f" Custom Code: No existing variant found. Attempting to create a new variant for size {size_id.name}.")

        # If no matching variant found, create one
        # This is done by creating the proper combination of template attribute values
        ptav_ids = []
        attr = size_id.attribute_id

        ptav = self.env['product.template.attribute.value'].search([
            ('product_tmpl_id', '=', product_tmpl.id),
            ('attribute_id', '=', attr.id),
            ('product_attribute_value_id', '=', size_id.id)
        ], limit=1)

        if ptav:
            ptav_ids.append(ptav.id)
            logging.info(f" Custom Code: Found product.template.attribute.value: {ptav.id} for size {size_id.name}")

        if len(ptav_ids) == 1:  # Only one attribute for grading
            logging.info(" Custom Code:Forcing variant creation via create_variant_ids()")
            product_tmpl.create_variant_ids()  # Ensure all combinations are generated

            # Search again after creation
            for variant in product_tmpl.product_variant_ids:
                variant_ptav_ids = variant.product_template_attribute_value_ids.ids
                logging.info(f" Custom Code: Post-creation: checking variant {variant.name} (ID {variant.id}) with ptav_ids: {variant_ptav_ids}")
                if all(ptav_id in variant_ptav_ids for ptav_id in ptav_ids):
                    logging.info(f" Custom Code: Successfully created/found variant {variant.name} (ID {variant.id}) for size {size_id.name}")
                    return variant

        logging.warning(f"Failed to find or create variant for Product Template: {product_tmpl.name} and Size: {size_id.name}")
        return False

    def _ensure_attribute_values_exist(self, product_tmpl, *values):
        """
        Ensure product.template.attribute.line exists for each value's attribute
        and includes that value, without triggering variant generation.
        Pass any number of attribute value records; falsy values are ignored.
        """
        ProductAttributeLine = self.env["product.template.attribute.line"]

        # Filter out None/False
        values = [v for v in values if v]
        if not product_tmpl or not values:
            return

        # Build a map: attribute_id -> set(value_ids)
        by_attr = {}
        for v in values:
            attr = v.attribute_id
            if not attr:
                continue
            by_attr.setdefault(attr.id, set()).add(v.id)

        if not by_attr:
            return

        # Fetch existing lines in one query
        lines = ProductAttributeLine.search([
            ("product_tmpl_id", "=", product_tmpl.id),
            ("attribute_id", "in", list(by_attr.keys())),
        ])
        line_by_attr = {l.attribute_id.id: l for l in lines}

        ctx = dict(self.env.context, create_product_product=False)

        creates = []
        for attr_id, value_ids in by_attr.items():
            line = line_by_attr.get(attr_id)
            if not line:
                creates.append({
                    "product_tmpl_id": product_tmpl.id,
                    "attribute_id": attr_id,
                    "value_ids": [(6, 0, list(value_ids))],
                })
            else:
                existing = set(line.value_ids.ids)
                missing = [vid for vid in value_ids if vid not in existing]
                if missing:
                    line.with_context(**ctx).write({
                        "value_ids": [(4, vid) for vid in missing]
                    })

        if creates:
            ProductAttributeLine.with_context(**ctx).create(creates)

    
    def _ensure_attribute_line(self, product_tmpl, attribute, value):
        """Ensure attribute line exists and contains the given value."""
        attr_line = self.env['product.template.attribute.line'].search([
            ('product_tmpl_id', '=', product_tmpl.id),
            ('attribute_id', '=', attribute.id)
        ], limit=1)

        if not attr_line:
            attr_line = self.env['product.template.attribute.line'].create({
                'product_tmpl_id': product_tmpl.id,
                'attribute_id': attribute.id,
                'value_ids': [(4, value.id)]
            })
        else:
            if value.id not in attr_line.value_ids.ids:
                attr_line.write({'value_ids': [(4, value.id)]})

        return attr_line

    def _find_or_create_variant_by_values(
        self,
        product_tmpl,
        values,
        *,
        log_prefix="VARIANT",
        apply_template_cost=True,
    ):
        """
        Find or create ONE specific variant defined by the given product.attribute.value records.
        - values: iterable of product.attribute.value records (can include None/False, they are ignored)
        - Never creates more than one variant
        - Avoids Odoo cross product by creating a single product.product with explicit PTAVs
        """
        ProductProduct = self.env["product.product"]
        PTAV = self.env["product.template.attribute.value"]

        # Normalize + filter
        values = [v for v in (values or []) if v]
        if not product_tmpl or not values:
            logging.warning("%s: Missing product_tmpl or values. Aborting.", log_prefix)
            return False

        target_value_ids = set(v.id for v in values)

        # ------------------------------------------------------------------
        # 1) Try to find existing
        # ------------------------------------------------------------------
        for variant in product_tmpl.product_variant_ids:
            variant_ptav = variant.product_template_attribute_value_ids
            variant_value_ids = set(variant_ptav.mapped("product_attribute_value_id").ids)

            logging.info(
                "%s: Variant [%s] (ID %s): PTAV IDs=%s | Value IDs=%s",
                log_prefix, variant.name, variant.id, variant_ptav.ids, variant_value_ids
            )

            if target_value_ids.issubset(variant_value_ids):
                logging.info(" Custom Code:%s: ✓ Matched existing variant %s (ID %s)", log_prefix, variant.name, variant.id)
                logging.info(" Custom Code:%s: END - FOUND EXISTING", log_prefix)
                logging.info(" Custom Code:------------------------------------------------------")
                return variant

        logging.info(" Custom Code:%s: ✗ No existing variant matched. Will create a new one.", log_prefix)

        # ------------------------------------------------------------------
        # 2) Ensure attribute lines + PTAVs exist for each value
        # ------------------------------------------------------------------
        ptav_ids = []
        for value in values:
            attr = value.attribute_id
            if not attr:
                continue

            logging.info(" Custom Code:%s: Ensuring attribute line exists for value '%s' (ID %s)", log_prefix, value.name, value.id)

            # Ensure attribute line has this value (your helper should NOT trigger cross product)
            attr_line = self._ensure_attribute_line(product_tmpl, attr, value)

            # Find existing PTAV
            ptav = PTAV.search([
                ("product_tmpl_id", "=", product_tmpl.id),
                ("attribute_id", "=", attr.id),
                ("product_attribute_value_id", "=", value.id),
            ], limit=1)

            if not ptav:
                logging.info(" Custom Code:%s: PTAV missing -> creating new PTAV for %s...", log_prefix, value.name)
                ptav = PTAV.create({
                    "product_tmpl_id": product_tmpl.id,
                    "attribute_id": attr.id,
                    "product_attribute_value_id": value.id,
                    "attribute_line_id": attr_line.id,
                })
                logging.info(" Custom Code:%s: New PTAV created: %s (ID %s)", log_prefix, ptav.name, ptav.id)
            else:
                logging.info(" Custom Code:%s: Existing PTAV found: %s (ID %s)", log_prefix, ptav.name, ptav.id)

            ptav_ids.append(ptav.id)

        if not ptav_ids:
            logging.warning("%s: Insufficient PTAVs to create variant! Aborting.", log_prefix)
            logging.info(" Custom Code:%s: END - FAILED", log_prefix)
            logging.info(" Custom Code:------------------------------------------------------")
            return False

        # ------------------------------------------------------------------
        # 3) Create EXACTLY ONE new variant
        # ------------------------------------------------------------------
        logging.info(" Custom Code:%s: Creating new variant with PTAV IDs: %s", log_prefix, ptav_ids)
        try:
            new_variant = ProductProduct.with_context(create_product_product=True).create({
                "product_tmpl_id": product_tmpl.id,
                "product_template_attribute_value_ids": [(6, 0, ptav_ids)],
            })

            logging.info(" Custom Code:%s: ✓ New variant created: %s (ID %s)", log_prefix, new_variant.name, new_variant.id)

            if apply_template_cost and getattr(product_tmpl, "cost_price", False):
                new_variant.standard_price = product_tmpl.cost_price
                logging.info(
                    "Custom Code: %s: -> Applied template cost price %s to variant %s",
                    log_prefix, product_tmpl.cost_price, new_variant.id
                )

            logging.info(" Custom Code:%s: END - CREATED NEW", log_prefix)
            logging.info(" Custom Code:------------------------------------------------------")
            return new_variant

        except Exception as e:
            logging.error("%s: ERROR creating variant: %s", log_prefix, e, exc_info=True)
            logging.info(" Custom Code:%s: END - ERROR", log_prefix)
            logging.info(" Custom Code:------------------------------------------------------")
            return False


    def _find_or_create_specific_garment_variant(self, product_tmpl, colorway_value, size_value):
        return self._find_or_create_variant_by_values(
            product_tmpl,
            values=[size_value, colorway_value],
            log_prefix="GARMENT VARIANT",
        )

    def _find_or_create_swatch_variant(self, product_tmpl, colorway_value, yarn_variant_value=None):
        return self._find_or_create_variant_by_values(
            product_tmpl,
            values=[colorway_value, yarn_variant_value],
            log_prefix="SWATCH VARIANT",
        )
    
    @api.depends('product_tmpl_id')
    def _compute_style_colorway_ids(self):
        """Compute available colorway IDs for the current style"""
        for record in self:
            if record.product_tmpl_id:
                style_colorways = self.env['style.colorway'].search([
                    ('product_tmpl_id', '=', record.product_tmpl_id.id),
                    ('active', '=', True)
                ])
                record.style_colorway_ids = style_colorways.mapped('colorway_id').ids
            else:
                record.style_colorway_ids = []

    @api.depends('product_tmpl_id')
    def _compute_style_size_ids(self):
        """Compute available sizes for the product template from style.size table"""
        for record in self:
            if record.product_tmpl_id:
                style_sizes = self.env['style.size'].search([
                    ('product_tmpl_id', '=', record.product_tmpl_id.id),
                    ('active', '=', True)
                ])
                record.style_size_ids = style_sizes.mapped('size_id').ids
            else:
                record.style_size_ids = []

    @api.model
    def _get_colorway_attribute(self):
        """Get the Colorway attribute"""
        return self.env['product.attribute'].search([('name', '=', 'Colorway')], limit=1)

    @api.depends('product_tmpl_id')
    def _compute_style_yarn_variant_ids(self):
        """Compute available yarn variants for the current style"""
        for record in self:
            if record.product_tmpl_id:
                style_yarns = self.env['style.yarn.variant'].search([
                    ('product_tmpl_id', '=', record.product_tmpl_id.id),
                    ('active', '=', True)
                ])
                record.style_yarn_variant_ids = style_yarns.mapped('yarn_variant_id').ids
            else:
                record.style_yarn_variant_ids = []
                
    def _create_colorway_value(self, name):
        """Create a new colorway attribute value"""
        colorway_attr = self._get_colorway_attribute()
        if colorway_attr:
            return self.env['product.attribute.value'].create({
                'name': name,
                'attribute_id': colorway_attr.id,
            })
        return False

    @api.model
    def _get_style_colorway_ids(self):
        """Get colorway IDs available for the current style - kept for backward compatibility"""
        if self._context.get('default_product_tmpl_id'):
            product_tmpl_id = self._context.get('default_product_tmpl_id')
            style_colorways = self.env['style.colorway'].search([
                ('product_tmpl_id', '=', product_tmpl_id),
                ('active', '=', True)
            ])
            return style_colorways.mapped('colorway_id').ids
        return []
