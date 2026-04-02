from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
from odoo.osv.expression import OR, AND

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # Common fields
    product_category = fields.Selection([
        ('yarn', 'Yarn'),
        ('garment', 'Garment'),
        ('swatch', 'Swatch'),
        ('services', 'Services'),
        ('yarn_book', 'Yarn Book'),
        ('misc', 'Misc')
    ], string='Product Category', default='misc', required=True)
    
    # Add is_storable field
    is_storable = fields.Boolean(string="Is Storable", default=True)
    
    # Add UOM selection field with only Kg and Units options
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', 
                           domain=[('id', 'in', [1, 12])],  # Limit to Units (1) and Kg (12)
                           default=lambda self: self._get_default_uom())
    # Common fields across categories
    brand_id = fields.Many2one('res.partner', string="Client")
    factory_id = fields.Many2one('res.partner', string="Factory", domain=[('contact_type', '=', 'factory')])
    hs_code = fields.Char(string="HS Code")
    company_id = fields.Many2one(
        'res.company', 'Lab', index=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Product Pricelist', default=lambda self: self.env['product.pricelist'].search([], limit=1)
    )
    display_currency_id = fields.Many2one(
    'res.currency', compute='_compute_display_currency', store=False)
    cost_price = fields.Monetary(
                                    string="Cost",
                                    currency_field='display_currency_id', 
                                    store=True,
                                )

    sales_price = fields.Float(string="Sales Price")
    invoice_policy = fields.Selection(
        selection=[
            ('order', "Ordered quantities"),
            ('delivery', "Delivered quantities"),
        ],
        string="Invoicing Policy",
        compute='_compute_invoice_policy',
        precompute=True,
        store=True,
        readonly=False,
        tracking=True,
        help="Ordered Quantity: Invoice quantities ordered by the customer.\n"
             "Delivered Quantity: Invoice quantities delivered to the customer.")
    # Yarn specific fields
    yarn_name = fields.Char(string="Yarn Name")
    vendor_id = fields.Many2one('res.partner', string="Vendor", domain=[('supplier_rank', '>', 0)])
    origin_country_id = fields.Many2one('res.country', string="Origin")
    yarn_count = fields.Char(string="Count")
    yarn_card = fields.Many2one(
        'product.template',
        string="Yarn Card",
        domain="[('product_category', '=', 'yarn_book')]"
    )
    # Yarn Book Field
    book_name = fields.Char(string="Book Name")    
    # One2many relationships
    fiber_ids = fields.One2many('product.fiber', 'product_tmpl_id', string="Fibers")
    color_ids = fields.One2many('product.color', 'product_tmpl_id', string="Colors")

    @api.constrains('fiber_ids')
    def _check_fiber_total(self):
        for tmpl in self:
            if not tmpl.fiber_ids:
                continue
            total = sum(tmpl.fiber_ids.mapped('percentage'))
            if abs(total - 100) > 0.01:
                raise ValidationError(f"Total fiber percentage must be 100% (currently {total}%).")
    yarn_stock_ids = fields.One2many('yarn.stock', 'product_tmpl_id', string="Yarn Stock")
    yarn_programming_ids = fields.One2many('yarn.programming', 'product_tmpl_id', string="Yarn Programming")
    
    # Text fields
    stock_information = fields.Text(string="Stock Information")
    programming_information = fields.Text(string="Programming Information")
    purchase_description = fields.Text(string='Purchase Description')
    
    # Attribute value fields (Many2many)
    garment_run_ids = fields.Many2many('product.attribute.value', 'product_tmpl_run_rel', 'product_tmpl_id', 'value_id', 
                                      string="Run", domain="[('attribute_id.name', '=', 'Run')]")
    garment_size_ids = fields.Many2many('product.attribute.value', 'product_tmpl_size_rel', 'product_tmpl_id', 'value_id', 
                                       string="Size", domain="[('attribute_id.name', '=', 'Size')]")
    garment_colorway_ids = fields.Many2many('product.attribute.value', 'product_tmpl_colorway_rel', 'product_tmpl_id', 'value_id', 
                                          string="Colorways", domain="[('attribute_id.name', '=', 'Colorway')]")
    swatch_number_ids = fields.Many2many('product.attribute.value', 'product_tmpl_swatch_num_rel', 'product_tmpl_id', 'value_id', 
                                        string="Swatch #", domain="[('attribute_id.name', '=', 'Swatch #')]")
    swatch_colorway_ids = fields.Many2many('product.attribute.value', 'product_tmpl_swatch_colorway_rel', 'product_tmpl_id', 'value_id', 
                                         string="Colorways", domain="[('attribute_id.name', '=', 'Colorway')]")
    
    # Computed fields for backward compatibility
    garment_run = fields.Char(string="Run", compute="_compute_garment_run", store=True)
    garment_size = fields.Char(string="Size", compute="_compute_garment_size", store=True)
    garment_colorways = fields.Char(string="Colorways", compute="_compute_garment_colorways", store=True)
    swatch_number = fields.Char(string="Swatch #", compute="_compute_swatch_number", store=True)
    swatch_colorways = fields.Char(string="Colorways", compute="_compute_swatch_colorways", store=True)
    
    # Misc, Service and Swatch specific fields
    misc_name = fields.Char(string='Misc Name')
    parent_project_id = fields.Many2one('crm.lead', string="Lead", domain=[('type', '=', 'opportunity')])
    swatch_package = fields.Text(string="Swatch Package")
    stitch_construction = fields.Text(string="Stitch Construction")
    style_family = fields.Char(string="Style Family")
    project_template_id = fields.Many2one(
        'project.project', 'Project Template', company_dependent=True, copy=True,
    )
    
    # BOM and variant related fields
    variants_from_bom = fields.Boolean(string="Variants from BOM", default=False)
    selected_run_id = fields.Many2one('product.attribute.value', string='Selected Run', 
                                     domain="[('attribute_id.name', '=', 'Run')]")
    selected_swatch_number_id = fields.Many2one('product.attribute.value', string='Selected Swatch #', 
                                               domain="[('attribute_id.name', '=', 'Swatch #')]")
    run_sizes = fields.Many2many('product.attribute.value', 'product_tmpl_run_sizes_rel', 'product_tmpl_id', 'value_id',
                                string='Sizes for Run', compute='_compute_run_attributes', store=False)
    run_colorways = fields.Many2many('product.attribute.value', 'product_tmpl_run_colorways_rel', 'product_tmpl_id', 'value_id',
                                    string='Colorways for Run', compute='_compute_run_attributes', store=False)
    swatch_colorways = fields.Many2many('product.attribute.value', 'product_tmpl_swatch_colorways_rel2', 'product_tmpl_id', 'value_id',
                                      string='Colorways for Swatch', compute='_compute_swatch_attributes', store=False)
    bom_count = fields.Integer(string='BOMs', compute='_compute_bom_count')
    is_cost_readonly = fields.Boolean(compute='_compute_is_cost_readonly')
    x_style_code = fields.Char(string='Style Code')
    x_number_of_colorways = fields.Integer(string='Number of Colorways')
    name = fields.Char(compute="_compute_name", store=True, readonly=False)
    service_category = fields.Selection([
        ('development', 'Development'),
        ('grading', 'Grading'),
        ('production', 'Production'),
        ('swatch', 'Swatch'),
    ])

    def _create_variant_ids(self):
        """
        For garment and swatch templates:
        - Skip Odoo's full attribute matrix generation
        - But still create the single default variant
        """
        ProductProduct = self.env['product.product']

        for tmpl in self:
            if tmpl.product_category in ('garment', 'swatch'):
                logging.info(
                    "Custom Code: Custom variant logic → Creating single variant for %s (ID %s)",
                    tmpl.name, tmpl.id
                )

                # If a variant already exists, do nothing
                if tmpl.product_variant_id:
                    continue

                # Create ONE default variant
                ProductProduct.create({
                    'product_tmpl_id': tmpl.id
                })

                # Skip parent's full variant generation
                continue

            # Normal behavior for non-garment templates
            super(ProductTemplate, tmpl)._create_variant_ids()

        return True

    @api.depends('vendor_id', 'yarn_count', 'yarn_name', 'product_category')
    def _compute_name(self):
        for rec in self:
            if rec.product_category == 'yarn':
                rec.name = rec._generate_yarn_name()

    @api.depends('pricelist_id.currency_id')
    def _compute_display_currency(self):
        default_currency = self.env.company.currency_id
        for r in self:
            r.display_currency_id = r.pricelist_id.currency_id or default_currency

    @api.onchange('pricelist_id')
    def _onchange_pricelist_id(self):
        self._compute_display_currency()

    # Simple computed fields
    @api.depends('product_category')
    def _compute_is_cost_readonly(self):
        for record in self:
            record.is_cost_readonly = record.product_category in ['garment', 'swatch']
    
    @api.depends('garment_run_ids')
    def _compute_garment_run(self):
        for record in self:
            record.garment_run = ', '.join(record.garment_run_ids.mapped('name'))
    
    def _get_service_uom(self):
        return self.env.ref('uom.product_uom_hour', raise_if_not_found=False) \
            or self.env['uom.uom'].search([('name', '=', 'Hours')], limit=1)
        
    @api.depends('garment_size_ids')
    def _compute_garment_size(self):
        for record in self:
            record.garment_size = ', '.join(record.garment_size_ids.mapped('name'))
    
    @api.depends('garment_colorway_ids')
    def _compute_garment_colorways(self):
        for record in self:
            record.garment_colorways = ', '.join(record.garment_colorway_ids.mapped('name'))
    
    @api.depends('swatch_number_ids')
    def _compute_swatch_number(self):
        for record in self:
            record.swatch_number = ', '.join(record.swatch_number_ids.mapped('name'))
    
    @api.depends('type')
    def _compute_invoice_policy(self):
        self.filtered(lambda t: t.type == 'consu' or not t.invoice_policy).invoice_policy = 'order'


    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        search_value = None
        base_domain = []

        # Extract the main 'name ilike' search value, if any
        for condition in domain:
            if isinstance(condition, (list, tuple)) and condition[0] == 'name' and condition[1] == 'ilike':
                search_value = condition[2]
            else:
                base_domain.append(condition)

        # Add extended OR conditions
        if search_value:
            or_conditions = [
                ('name', 'ilike', search_value),
                ('brand_id.name', 'ilike', search_value),
                ('factory_id.name', 'ilike', search_value),
                ('hs_code', 'ilike', search_value),
                ('style_family', 'ilike', search_value),
                ('parent_project_id.name', 'ilike', search_value),
            ]
            try:
                val = float(search_value)
                or_conditions += [
                    ('list_price', '=', val),
                    ('standard_price', '=', val)
                ]
            except ValueError:
                pass

            domain = base_domain + OR([[cond] for cond in or_conditions])

        return super()._search(domain, offset=offset, limit=limit, order=order)

    @api.depends('swatch_colorway_ids')
    def _compute_swatch_colorways(self):
        for record in self:
            record.swatch_colorways = ', '.join(record.swatch_colorway_ids.mapped('name'))
    
    @api.depends('bom_ids')
    def _compute_bom_count(self):
        for record in self:
            record.bom_count = len(record.bom_ids)
    
    # BOM-related computed fields
    @api.depends('selected_run_id', 'bom_ids', 'bom_ids.run_id', 'bom_ids.size_id', 'bom_ids.colorway_id', 'bom_ids.total_cost')
    def _compute_run_attributes(self):
        for record in self:
            run_sizes = self.env['product.attribute.value']
            run_colorways = self.env['product.attribute.value']
            
            if record.selected_run_id and record.product_category == 'garment':
                boms = self.env['mrp.bom'].search([
                    ('product_tmpl_id', '=', record.id),
                    ('run_id', '=', record.selected_run_id.id)
                ])
                
                run_sizes = boms.mapped('size_id')
                run_colorways = boms.mapped('colorway_id')
                
                # Update cost from the BOM
                if boms:
                    main_bom = boms[0]
                    if main_bom.total_cost > 0:
                        record.cost_price = main_bom.total_cost
                        record.standard_price = main_bom.total_cost
                    else:
                        main_bom._compute_total_cost()
                        if main_bom.total_cost > 0:
                            record.cost_price = main_bom.total_cost
                            record.standard_price = main_bom.total_cost
            
            record.run_sizes = run_sizes
            record.run_colorways = run_colorways
    
    @api.depends('selected_swatch_number_id', 'bom_ids', 'bom_ids.swatch_number_id', 'bom_ids.colorway_id', 'bom_ids.total_cost')
    def _compute_swatch_attributes(self):
        for record in self:
            swatch_colorways = self.env['product.attribute.value']
            
            if record.selected_swatch_number_id and record.product_category == 'swatch':
                boms = self.env['mrp.bom'].search([
                    ('product_tmpl_id', '=', record.id),
                    ('swatch_number_id', '=', record.selected_swatch_number_id.id)
                ])

                swatch_colorways = boms.mapped('colorway_id')
                
                # Update cost from the BOM
                if boms:
                    main_bom = boms[0]
                    if main_bom.total_cost > 0:
                        record.cost_price = main_bom.total_cost
                        record.standard_price = main_bom.total_cost
                    else:
                        main_bom._compute_total_cost()
                        if main_bom.total_cost > 0:
                            record.cost_price = main_bom.total_cost
                            record.standard_price = main_bom.total_cost
            
            record.swatch_colorways = swatch_colorways
    
    # Method to get the corresponding product.category for a product_category selection value
    def _get_product_category_id(self, product_category_value):
        """Get the product.category record that corresponds to the product_category selection value"""
        if not product_category_value:
            return False
            
        # Map selection values to XML IDs
        xml_id_map = {
            'yarn': 'maeknit_inventory_customization.product_category_yarn',
            'yarn_book': 'maeknit_inventory_customization.product_category_yarn_book',
            'garment': 'maeknit_inventory_customization.product_category_garment',
            'swatch': 'maeknit_inventory_customization.product_category_swatch',
            'services': 'maeknit_inventory_customization.product_category_services',
            'misc': 'maeknit_inventory_customization.product_category_misc',
        }
        
        xml_id = xml_id_map.get(product_category_value)
        if not xml_id:
            return False
            
        # Try to get the category by XML ID
        category = self.env.ref(xml_id, raise_if_not_found=False)
        
        # If not found by XML ID, try to find by name
        if not category:
            category_name = dict(self._fields['product_category'].selection).get(product_category_value)
            category = self.env['product.category'].search([('name', '=', category_name)], limit=1)
            
        return category.id if category else False
    
    # Method to get the product_category selection value from a product.category record
    def _get_product_category_value(self, categ_id):
        """Get the product_category selection value that corresponds to the product.category record"""
        if not categ_id:
            return 'misc'  # Default to misc if no category
            
        # Get the category record
        category = self.env['product.category'].browse(categ_id)
        if not category.exists():
            return 'misc'
            
        # Map category names to selection values
        name_map = {
            'Yarn': 'yarn',
            'Yarn Book': 'yarn_book',
            'Garment': 'garment',
            'Swatch': 'swatch',
            'Services': 'services',
            'Misc': 'misc',
        }
        
        return name_map.get(category.name, 'misc')
    
    # Onchange handlers
    @api.onchange('product_category')
    def _onchange_product_category(self):
        # Store the current name before changing anything
        current_name = self.name
        current_yarn_name = self.yarn_name or self.name
        route_ids = self._get_default_routes(self.product_category)
        if route_ids:
            self.route_ids = [(6, 0, route_ids)]

        self.type = 'service' if self.product_category == 'services' else 'consu'
        
        # Set is_storable based on product category
        self.is_storable = self.product_category != 'services'
        
        # Set UOM based on product category
        kg_uom = self.env.ref('uom.product_uom_kgm', raise_if_not_found=False) or self.env['uom.uom'].search([('id', '=', 12)], limit=1)
        unit_uom = self.env.ref('uom.product_uom_unit', raise_if_not_found=False) or self.env['uom.uom'].search([('id', '=', 1)], limit=1)
        hour_uom = self.env.ref('uom.product_uom_hour', raise_if_not_found=False) or self.env['uom.uom'].search([('name', '=', 'Hours')], limit=1)


        # Sync with standard Odoo category
        categ_id = self._get_product_category_id(self.product_category)
        if categ_id:
            self.categ_id = categ_id
            
        category = self.env.context.get('default_product_category') or self.product_category
        
        if category == 'yarn':
            logging.info(" Custom Code:Onchange: Setting UoM to Kg for Yarn product")
            self.uom_id = kg_uom.id if kg_uom else 12  # Default to Kg
            self.uom_po_id = kg_uom.id if kg_uom else 12
            if current_name and not current_yarn_name:
                self.yarn_name = current_name

        elif self.product_category == 'services':
            self.uom_id = hour_uom.id if hour_uom else self.uom_id  # Avoid override if fallback fails

        else:
            self.uom_id = unit_uom.id if unit_uom else 1  # Default to Units
            if current_yarn_name and not current_name and self._origin.product_category == 'yarn':
                self.name = current_yarn_name

        # Set tracking to 'lot' for yarn products
        category = self.env.context.get('default_product_category') or self.product_category        
        if category == 'yarn':
            self.tracking = 'lot'
            if not (self.name and self.name.strip()):
                # Use yarn_name if already set
                if self.yarn_name:
                    self.name = self.yarn_name
                # OR fallback to current_name
                elif current_yarn_name:
                    self.name = current_yarn_name

            # Keep yarn_name in sync
            if not self.yarn_name and self.name:
                self.yarn_name = self.name

            # NOW generate final yarn name
            self.name = self._generate_yarn_name()
        else:
            self.tracking = 'none'
        
        # Set variants_from_bom flag for garment and swatch products
        if self.product_category in ['garment', 'swatch']:
            self.variants_from_bom = True
            self.cost_price = 0.0
    
    @api.onchange('name')
    def _onchange_name_to_yarn_name(self):
        """Copy name to yarn_name when name is entered in quick create"""
        for rec in self:
            if rec.product_category == 'yarn' and rec.name and not rec.yarn_name:
                rec.yarn_name = rec.name
                logging.info(f'Onchange name: Copied name "{rec.name}" to yarn_name')
    @api.onchange('categ_id')
    def _onchange_categ_id(self):
        """When the standard Odoo category changes, update our custom product_category field"""
        if self.categ_id:
            # Get the corresponding product_category value
            product_category_value = self._get_product_category_value(self.categ_id.id)
            
            # Only update if it's different to avoid infinite recursion
            if product_category_value != self.product_category:
                self.product_category = product_category_value
    
    @api.onchange('selected_run_id')
    def _onchange_selected_run(self):
        if self.product_category == 'garment':
            # Get the real ID if this is a new record
            real_id = self._origin.id if self._origin else False
            
            if not real_id:
                return
                
            logging.info(f" Custom Code: Searching for BOMs with product_tmpl_id={real_id}")
            
            # Find all BOMs for this product with the selected run
            if self.selected_run_id:
                boms = self.env['mrp.bom'].search([
                    ('product_tmpl_id', '=', real_id),
                    ('run_id', '=', self.selected_run_id.id)
                ])
                
                logging.info(f" Custom Code: Found {len(boms)} BOMs for Run ID {self.selected_run_id.id}")
                
                # Get sizes and colorways from BOMs
                sizes = boms.mapped('size_id')
                colorways = boms.mapped('colorway_id')
                
                logging.info(f" Custom Code: Sizes: {sizes.mapped('name')}")
                logging.info(f" Custom Code: Colorways: {colorways.mapped('name')}")
                
                # Update the fields
                self.run_sizes = [(6, 0, sizes.ids)]
                self.run_colorways = [(6, 0, colorways.ids)]
                
                # Update cost from the first BOM
                if boms:
                    main_bom = boms[0]
                    if main_bom.total_cost > 0:
                        self.cost_price = main_bom.total_cost
                        self.standard_price = main_bom.total_cost
                    else:
                        # Force computation of total cost
                        main_bom._compute_total_cost()
                        if main_bom.total_cost > 0:
                            self.cost_price = main_bom.total_cost
                            self.standard_price = main_bom.total_cost
                else:
                    self.cost_price = 0.0
                    self.standard_price = 0.0
            else:
                # Clear the fields if no run is selected
                self.run_sizes = [(5, 0, 0)]
                self.run_colorways = [(5, 0, 0)]
                self.cost_price = 0.0
                self.standard_price = 0.0
    
    @api.onchange('selected_swatch_number_id')
    def _onchange_selected_swatch_number(self):
        if self.product_category == 'swatch':
            # Get the real ID if this is a new record
            real_id = self._origin.id if self._origin else False
            
            if not real_id:
                return
                
            logging.info(f" Custom Code: Searching for BOMs with product_tmpl_id={real_id}")
            
            # Find all BOMs for this product with the selected swatch number
            if self.selected_swatch_number_id:
                boms = self.env['mrp.bom'].search([
                    ('product_tmpl_id', '=', real_id),
                    ('swatch_number_id', '=', self.selected_swatch_number_id.id)
                ])
                
                logging.info(f" Custom Code: Found {len(boms)} BOMs for Swatch # ID {self.selected_swatch_number_id.id}")
                
                # Get colorways from BOMs
                colorways = boms.mapped('colorway_id')
                
                logging.info(f" Custom Code: Colorways: {colorways.mapped('name')}")
                
                # Update the fields
                self.swatch_colorways = [(6, 0, colorways.ids)]
                
                # Update cost from the first BOM
                if boms:
                    main_bom = boms[0]
                    if main_bom.total_cost > 0:
                        self.cost_price = main_bom.total_cost
                        self.standard_price = main_bom.total_cost
                    else:
                        # Force computation of total cost
                        main_bom._compute_total_cost()
                        if main_bom.total_cost > 0:
                            self.cost_price = main_bom.total_cost
                            self.standard_price = main_bom.total_cost
                else:
                    self.cost_price = 0.0
                    self.standard_price = 0.0
            else:
                # Clear the fields if no swatch number is selected
                self.swatch_colorways = [(5, 0, 0)]
                self.cost_price = 0.0
                self.standard_price = 0.0
    
    @api.onchange('vendor_id', 'yarn_count', 'yarn_name')
    def _onchange_yarn_fields(self):
        category = self.env.context.get('default_product_category') or self.product_category
        if category == 'yarn':
            self.name = self._generate_yarn_name()
            self.origin_country_id = self.vendor_id.country_id
        
    @api.onchange('book_name')
    def _onchange_yarn_book_fields(self):
        if self.product_category == 'yarn_book':
            self.name = self.book_name
                
    @api.onchange('cost_price')
    def _onchange_cost_price(self):
        self.standard_price = self.cost_price
    
    @api.onchange('sales_price')
    def _onchange_sales_price(self):
        self.list_price = self.sales_price
    
    @api.onchange('standard_price')
    def _onchange_standard_price(self):
        self.cost_price = self.standard_price
    
    @api.onchange('list_price')
    def _onchange_list_price(self):
        self.sales_price = self.list_price
    

    # Helper methods
    def _generate_yarn_name(self):
        vendor_name = self.vendor_id.name if self.vendor_id else ''
        count = self.yarn_count or ''
        yarn_name = self.yarn_name or ''
        
        name_parts = [p for p in [vendor_name, count, yarn_name] if p]
        
        # Remove duplicates while preserving order
        unique_parts = []
        for part in name_parts:
            if part not in unique_parts:
                unique_parts.append(part)
                
        return " - ".join(unique_parts) if unique_parts else ""
    
    def _get_or_create_attribute(self, name):
        ProductAttribute = self.env['product.attribute']
        attribute = ProductAttribute.search([('name', '=', name)], limit=1)
        if not attribute:
            attribute = ProductAttribute.create({
                'name': name,
                'create_variant': 'no_variant',  # Changed from 'always' to 'no_variant'
                'display_type': 'select'
            })
        return attribute
    
    def _get_or_create_attribute_value(self, attribute, value):
        ProductAttributeValue = self.env['product.attribute.value']
        attr_value = ProductAttributeValue.search([
            ('attribute_id', '=', attribute.id),
            ('name', '=', value)
        ], limit=1)
        
        if not attr_value:
            attr_value = ProductAttributeValue.create({
                'attribute_id': attribute.id,
                'name': value
            })
        
        return attr_value
    
    def _sync_yarn_stock_from_colors(self, record):
        YarnStock = self.env['yarn.stock']
        existing_stock = YarnStock.search([('product_tmpl_id', '=', record.id)])

        # Create a dictionary of existing stock entries by color
        existing_by_color = {(stock.technical_color or '', stock.generic_color or ''): stock for stock in existing_stock}

        # Process each color
        for color in record.color_ids:
            key = (color.technical or '', color.generic or '')
            if key not in existing_by_color:
                YarnStock.create({
                    'product_tmpl_id': record.id,
                    'technical_color': color.technical,
                    'generic_color': color.generic,
                    'lot_number': '1',  # Default lot number
                    'cost': color.cost or record.standard_price or 0.0,  # Sync cost from color or product
                })
    
    def _update_variant_costs(self, variants, cost_price):
        """Update cost price on variants"""
        if variants and cost_price:
            # For yarn products, skip updating variant costs here
            # Individual costs are managed via yarn.stock records
            if self.product_category == 'yarn':
                logging.info(f" Custom Code: Skipping variant cost update for yarn product - costs managed by yarn.stock")
                return

            variants.write({'standard_price': cost_price})
            logging.info(f" Custom Code: Updated cost price for {len(variants)} variants to {cost_price}")

    def _sync_all_yarn_costs_to_variants(self):
        """Sync costs from all yarn.stock records to variants"""
        self.ensure_one()
        YarnStock = self.env['yarn.stock']
        yarn_stocks = YarnStock.search([('product_tmpl_id', '=', self.id)])
        logging.info(f" Custom Code: Syncing {len(yarn_stocks)} yarn.stock records to variants")
        for yarn_stock in yarn_stocks:
            yarn_stock._sync_cost_to_variants()
    
    def _create_single_value_attribute_line(self, template, attribute, value):
        """Create an attribute line with a single value"""
        ProductAttributeLine = self.env['product.template.attribute.line']
        
        # Check if an attribute line already exists for this attribute
        attr_line = ProductAttributeLine.search([
            ('product_tmpl_id', '=', template.id),
            ('attribute_id', '=', attribute.id)
        ], limit=1)
        
        if not attr_line:
            # Create new attribute line
            ProductAttributeLine.create({
                'product_tmpl_id': template.id,
                'attribute_id': attribute.id,
                'value_ids': [(6, 0, [value.id])]
            })
        elif value.id not in attr_line.value_ids.ids:
            # Add the value to existing attribute line
            attr_line.write({
                'value_ids': [(4, value.id)]
            })
    
    # CRUD methods
    @api.model_create_multi
    def create(self, vals_list):
        records = self.env['product.template']
        for vals in vals_list:
            # Set default product_category if not provided
            # Check context first (e.g. when quick-creating from Swatch BOM Req, context has default_product_category='swatch')
            if 'product_category' not in vals:
                vals['product_category'] = self.env.context.get('default_product_category') or 'garment'
                logging.info(f" Custom Code: Product created without category, defaulting to '{vals['product_category']}': {vals.get('name', 'Unknown')}")

            if 'product_category' in vals and 'route_ids' not in vals:
                default_routes = self._get_default_routes(vals['product_category'])
                if default_routes:
                    vals['route_ids'] = [(6, 0, default_routes)]

            if vals.get('product_category') == 'yarn':
                vals['categ_id'] = self._get_product_category_id('yarn')
            elif vals.get('product_category') == 'book':
                vals['categ_id'] = self._get_product_category_id('book')
            elif vals.get('product_category') == 'garment':
                vals['categ_id'] = self._get_product_category_id('garment')
            elif vals.get('product_category') == 'swatch':
                vals['categ_id'] = self._get_product_category_id('swatch')
            elif vals.get('product_category') == 'services':
                vals['categ_id'] = self._get_product_category_id('services')
            elif vals.get('product_category') == 'misc':
                vals['categ_id'] = self._get_product_category_id('misc')
        
            # Handle name synchronization between name and yarn_name
            if vals.get('product_category') == 'yarn':
                if not vals.get('yarn_name') and vals.get('name'):
                    vals['yarn_name'] = vals.get('name')
                if not vals.get('name'):
                    temp_record = self.new(vals)
                    vals['name'] = temp_record._generate_yarn_name()
            else:
                if not vals.get('name') and vals.get('yarn_name'):
                    vals['name'] = vals['yarn_name']
                elif not vals.get('name') and vals.get('book_name'):
                    vals['name'] = vals['book_name']
                elif not vals.get('name'):
                    category = vals.get('product_category', 'misc')
                    vals['name'] = f"New {category.capitalize()} Product"

            # Set is_storable
            if 'product_category' in vals and 'is_storable' not in vals:
                vals['is_storable'] = vals['product_category'] != 'services'

            # UOM setup
            if 'product_category' in vals and 'uom_id' not in vals:
                kg_uom = self.env.ref('uom.product_uom_kgm', raise_if_not_found=False)
                unit_uom = self.env.ref('uom.product_uom_unit', raise_if_not_found=False)
                if vals['product_category'] == 'yarn':
                    vals['uom_id'] = kg_uom.id if kg_uom else 12
                    vals['uom_po_id'] = kg_uom.id if kg_uom else 12
                else:
                    vals['uom_id'] = unit_uom.id if unit_uom else 1
                    vals['uom_po_id'] = unit_uom.id if unit_uom else 1
                if vals.get('product_category') == 'services':
                    uom = self._get_service_uom()
                    if uom:
                        vals['uom_id'] = uom.id
                        vals['uom_po_id'] = uom.id

            # Tracking rules
            if vals.get('product_category') == 'yarn' and 'tracking' not in vals:
                vals['tracking'] = 'lot'
            elif 'product_category' in vals and vals['product_category'] != 'yarn' and 'tracking' not in vals:
                vals['tracking'] = 'none'

            # Price sync
            if 'cost_price' in vals and 'standard_price' not in vals:
                vals['standard_price'] = vals['cost_price']
            if 'sales_price' in vals and 'list_price' not in vals:
                vals['list_price'] = vals['sales_price']

            # Service type
            if vals.get('product_category') == 'services':
                vals['type'] = 'service'

            # BOM flag
            if vals.get('product_category') in ['garment', 'swatch']:
                vals['variants_from_bom'] = True

            # Category sync
            if 'product_category' in vals and 'categ_id' not in vals:
                categ_id = self._get_product_category_id(vals['product_category'])
                if categ_id:
                    vals['categ_id'] = categ_id
            elif 'categ_id' in vals and 'product_category' not in vals:
                product_category = self._get_product_category_value(vals['categ_id'])
                if product_category:
                    vals['product_category'] = product_category

        # Create records in one call
        records = super(ProductTemplate, self).create(vals_list)

        # Post-creation logic (can handle multiple)
        for record in records:
            if record.product_category not in ['garment', 'swatch'] or not record.variants_from_bom:
                self._create_variants_for_record(record)
            if record.product_category == 'yarn' and record.color_ids:
                self._sync_yarn_stock_from_colors(record)
            if record.factory_id or record.vendor_id:
                record._update_vendor_info()

        return records

    
    def write(self, vals):
        # Update is_storable if product_category changes
        if 'product_category' in vals:
            vals['is_storable'] = vals['product_category'] != 'services'
            
            if 'route_ids' not in vals:
                default_routes = self._get_default_routes(vals['product_category'])
                if default_routes:
                    vals['route_ids'] = [(6, 0, default_routes)]

            # Handle name preservation when changing categories
            if vals['product_category'] == 'yarn' and 'yarn_name' not in vals:
                # If switching to yarn and yarn_name is not provided, use the current name
                for record in self:
                    if record.name and not record.yarn_name:
                        vals['yarn_name'] = record.name
            elif vals['product_category'] != 'yarn' and 'name' not in vals:
                # If switching from yarn to another category and name is not provided, use yarn_name
                for record in self:
                    if record.product_category == 'yarn' and record.yarn_name and not vals.get('name'):
                        vals['name'] = record.yarn_name
            
            # Sync with standard Odoo category
            categ_id = self._get_product_category_id(vals['product_category'])
            if categ_id and ('categ_id' not in vals or vals.get('categ_id') != categ_id):
                vals['categ_id'] = categ_id
        
        # If standard Odoo category changes, sync with our custom product_category
        if 'categ_id' in vals and 'product_category' not in vals:
            for record in self:
                product_category = record._get_product_category_value(vals['categ_id'])
                if product_category and product_category != record.product_category:
                    vals['product_category'] = product_category
                    
                    # Now that we've added product_category to vals, we need to handle the related changes
                    vals['is_storable'] = product_category != 'services'
                    
                    # Update UOM based on product category
                    kg_uom = self.env.ref('uom.product_uom_kgm', raise_if_not_found=False) or self.env['uom.uom'].search([('id', '=', 12)], limit=1)
                    unit_uom = self.env.ref('uom.product_uom_unit', raise_if_not_found=False) or self.env['uom.uom'].search([('id', '=', 1)], limit=1)
                
                    if product_category == 'yarn':
                        vals['uom_id'] = kg_uom.id if kg_uom else 12  # Default to Kg for yarn
                        vals['uom_po_id'] = kg_uom.id if kg_uom else 12
                    else:
                        vals['uom_id'] = unit_uom.id if unit_uom else 1  # Default to Units for others
                        vals['uom_po_id'] = unit_uom.id if unit_uom else 1
                    
                    # Update tracking when product category changes
                    if product_category == 'yarn':
                        vals['tracking'] = 'lot'
                    else:
                        vals['tracking'] = 'none'
                    
                    # Set variants_from_bom flag for garment and swatch products
                    if product_category in ['garment', 'swatch']:
                        vals['variants_from_bom'] = True
        
        # Update tracking when product category changes
        if 'product_category' in vals:
            if vals['product_category'] == 'yarn' and 'tracking' not in vals:
                vals['tracking'] = 'lot'
            elif 'tracking' not in vals:
                vals['tracking'] = 'none'
    
        # Sync price fields
        if 'cost_price' in vals and 'standard_price' not in vals:
            vals['standard_price'] = vals['cost_price']
        if 'sales_price' in vals and 'list_price' not in vals:
            vals['list_price'] = vals['sales_price']
        
        # Update name for yarn products
        if any(record.product_category == 'yarn' for record in self) and any(field in vals for field in ['vendor_id', 'yarn_count', 'yarn_name']):
            for record in self:
                if record.product_category == 'yarn':
                    temp_vals = record.copy_data()[0]
                    for field in vals:
                        temp_vals[field] = vals[field]
                    temp_record = self.new(temp_vals)
                    vals['name'] = temp_record._generate_yarn_name()
        
        # Check if colors are being updated
        color_update = 'color_ids' in vals
        
        # Ensure variants_from_bom is always True for garment and swatch products
        if 'product_category' in vals and vals['product_category'] in ['garment', 'swatch']:
            vals['variants_from_bom'] = True
        elif 'variants_from_bom' in vals and any(record.product_category in ['garment', 'swatch'] for record in self):
            # If trying to change variants_from_bom for garment/swatch products, force it to True
            for record in self:
                if record.product_category in ['garment', 'swatch']:
                    vals['variants_from_bom'] = True
        
        result = super(ProductTemplate, self).write(vals)

        # Sync name back to linked CRM lead via style_family (avoid infinite loop)
        # Only sync to child/style leads — never overwrite the collection name
        if 'name' in vals and not self.env.context.get('_syncing_product_name'):
            for record in self:
                if record.product_category in ['garment', 'swatch'] and record.style_family:
                    leads = self.env['crm.lead'].search([
                        ('style_family', '=', record.style_family),
                        ('x_project_type', '!=', 'collection'),
                    ])
                    if leads:
                        leads.with_context(_syncing_product_name=True).write({
                            'name': vals['name']
                        })

        # Update variant costs if cost_price changed
        if 'cost_price' in vals:
            for template in self:
                self._update_variant_costs(template.product_variant_ids, template.cost_price)
        
        # Update variants if relevant fields changed
        variant_fields = ['garment_run_ids', 'garment_size_ids', 'garment_colorway_ids', 
                         'swatch_number_ids', 'swatch_colorway_ids', 'color_ids']
        
        if any(field in vals for field in variant_fields):
            for record in self:
                if record.product_category not in ['garment', 'swatch'] or not record.variants_from_bom:
                    self._create_variants_for_record(record)
        
        # Sync yarn stock if colors were updated
        if color_update:
            for record in self.filtered(lambda r: r.product_category == 'yarn'):
                self._sync_yarn_stock_from_colors(record)
        
        # Update vendor info if factory or vendor changed
        if 'factory_id' in vals or 'vendor_id' in vals:
            for record in self:
                record._update_vendor_info()

        return result
    
    # Variant creation methods
    def _create_variants_for_record(self, record):
        """Unified method to create variants based on product category"""
        if not record:
            return
            
        if record.product_category == 'garment' and not record.variants_from_bom:
            self._create_attribute_based_variants(
                record, 
                'Run', record.garment_run_ids,
                'Size', record.garment_size_ids,
                'Colorway', record.garment_colorway_ids
            )
        elif record.product_category == 'swatch' and not record.variants_from_bom:
            self._create_attribute_based_variants(
                record, 
                'Swatch #', record.swatch_number_ids,
                'Colorway', record.swatch_colorway_ids
            )
        elif record.product_category == 'yarn':
            self._create_yarn_variants(record)
    
    def _create_attribute_based_variants(self, record, *args):
        """Create variants based on attribute values
        Args should be pairs of attribute_name and values
        Example: 'Run', run_values, 'Size', size_values
        """
        # Check if we have any values
        has_values = False
        attribute_lines = []
        
        # Process attribute pairs
        for i in range(0, len(args), 2):
            if i + 1 < len(args):
                attr_name = args[i]
                attr_values = args[i + 1]
                
                if attr_values:
                    has_values = True
                    attr = self._get_or_create_attribute(attr_name)
                    attribute_lines.append((0, 0, {
                        'attribute_id': attr.id,
                        'value_ids': [(6, 0, attr_values.ids)]
                    }))
        
        if not has_values:
            return
        
        # Update product template with attribute lines
        if attribute_lines:
            # Remove existing attribute lines
            record.attribute_line_ids.unlink()
            
            # Add new attribute lines
            record.write({'attribute_line_ids': attribute_lines})
            
            # Force creation of variants
            try:
                self.env['product.template'].invalidate_model(['product_variant_ids'])
                self.env['product.product'].flush_model()
                self.env['product.template'].flush_model()
                record._create_variant_ids()

                # Update cost price on all variants
                self._update_variant_costs(record.product_variant_ids, record.cost_price)

                # For yarn products, sync all yarn.stock costs to variants
                if record.product_category == 'yarn':
                    record._sync_all_yarn_costs_to_variants()

                self.env.cr.commit()
            except Exception as e:
                logging.error(f"Error creating variants: {str(e)}")
                self.env.cr.rollback()
    
    def _create_yarn_variants(self, record):
        """Create variants for yarn products based on colors"""
        if not record.color_ids:
            return
        
        color_attr = self._get_or_create_attribute('Color')
        color_values = []
        
        # Create attribute values for each color
        for color in record.color_ids:
            # Create a combined name from technical and generic
            color_name = color.technical
            if color.generic:
                color_name = f"{color_name} ({color.generic})" if color_name else color.generic
            
            if color_name:
                color_value = self._get_or_create_attribute_value(color_attr, color_name)
                color_values.append(color_value.id)
        
        # Update product template with attribute lines
        if color_values:
            # Remove existing attribute lines
            record.attribute_line_ids.unlink()
            
            # Add new attribute lines
            record.write({
                'attribute_line_ids': [(0, 0, {
                    'attribute_id': color_attr.id,
                    'value_ids': [(6, 0, color_values)]
                })]
            })
            
            # Force creation of variants
            try:
                self.env['product.template'].invalidate_model(['product_variant_ids'])
                self.env['product.product'].flush_model()
                self.env['product.template'].flush_model()
                record._create_variant_ids()

                # Update cost price on all variants
                self._update_variant_costs(record.product_variant_ids, record.cost_price)

                # For yarn products, sync all yarn.stock costs to variants
                if record.product_category == 'yarn':
                    record._sync_all_yarn_costs_to_variants()

                self.env.cr.commit()
            except Exception as e:
                logging.error(f"Error creating yarn variants: {str(e)}")
                self.env.cr.rollback()
    
    # Override standard methods
    def create_variant_ids(self):
        """Override to prevent automatic cartesian product variant creation"""
        for template in self:
            if template.product_category in ['garment', 'swatch'] and template.variants_from_bom:
                # Don't create variants automatically - they will be created when BOMs are created
                logging.info(f" Custom Code: Skipping automatic variant creation for {template.name} - variants created from BOMs only")
                continue
            else:
                # For other products, use the standard variant creation
                super(ProductTemplate, template).create_variant_ids()
        
        return True

    def _create_variants_from_boms(self, template):
        """Create product variants only for the specific combinations defined in BOMs"""
        # Get all BOMs for this template
        boms = self.env['mrp.bom'].search([('product_tmpl_id', '=', template.id)])
        
        if not boms:
            return
        
        for bom in boms.filtered(lambda b: b.is_garment_bom):
            if bom.colorway_id and bom.size_id:  # colorway + size are required
                variant = self.env['mrp.bom']._find_or_create_specific_garment_variant(
                    template, bom.run_id, bom.colorway_id, bom.size_id
                )
                if variant and template.cost_price:
                    variant.standard_price = template.cost_price
        
        # Process swatch BOMs
        for bom in boms.filtered(lambda b: b.is_swatch_bom):
            if bom.swatch_number_id and bom.colorway_id:
                variant = self.env['mrp.bom']._find_or_create_swatch_variant(
                    template, bom.swatch_number_id, bom.colorway_id
                )
                if variant and template.cost_price:
                    variant.standard_price = template.cost_price
    def _update_attribute_lines_from_boms(self, template, boms):
        """Update attribute lines to only include values used in BOMs"""
        if not (template.product_category in ['garment', 'swatch'] and template.variants_from_bom):
            return
        
        # Get or create attributes
        run_attr = self._get_or_create_attribute('Run')
        size_attr = self._get_or_create_attribute('Size')
        colorway_attr = self._get_or_create_attribute('Colorway')
        swatch_num_attr = self._get_or_create_attribute('Swatch #')
        
        # Remove existing attribute lines
        template.attribute_line_ids.unlink()
        
        # For garment products
        if template.product_category == 'garment':
            # Create attribute lines for each BOM
            for bom in boms.filtered(lambda b: b.is_garment_bom):
                if bom.run_id and bom.colorway_id and bom.size_id:
                    self._create_single_value_attribute_line(template, run_attr, bom.run_id)
                    self._create_single_value_attribute_line(template, colorway_attr, bom.colorway_id)
                    self._create_single_value_attribute_line(template, size_attr, bom.size_id)
        
        # For swatch products
        elif template.product_category == 'swatch':
            # Create attribute lines for each BOM
            for bom in boms.filtered(lambda b: b.is_swatch_bom):
                if bom.swatch_number_id and bom.colorway_id:
                    self._create_single_value_attribute_line(template, swatch_num_attr, bom.swatch_number_id)
                    self._create_single_value_attribute_line(template, colorway_attr, bom.colorway_id)
    
    @api.model
    def create_variant_product_list(self, template_id, variant_ids):
        """Override to set cost price on new variants"""
        variants = super(ProductTemplate, self).create_variant_product_list(template_id, variant_ids)
        
        # Get the template's cost price
        template = self.browse(template_id)
        if template and template.cost_price:
            # Set the cost price on all new variants
            for variant in variants:
                variant.standard_price = template.cost_price
        
        return variants
    def action_view_boms_custom(self):
        """Custom method to view BOMs based on product category"""
        self.ensure_one()
        action = self.env.ref('mrp.mrp_bom_form_action').read()[0]
        action['domain'] = [('product_tmpl_id', '=', self.id)]
        action['context'] = {
            'default_product_tmpl_id': self.id,
            'default_is_garment_bom': self.product_category == 'garment',
            'default_is_swatch_bom': self.product_category == 'swatch'
        }
        logging.info(f" Custom Code: Action view BOM called for product category: {self.product_category}")

        return action
    
    def action_create_bom(self):
        """Create a new BOM for this product with the selected Run or Swatch #"""
        self.ensure_one()
        
        if self.product_category == 'garment':
            if not self.selected_run_id:
                raise ValidationError("Please select a Run before creating a BOM.")
            
            action = self.env.ref('mrp.mrp_bom_form_action').read()[0]
            action['views'] = [(self.env.ref('mrp.mrp_bom_form_view').id, 'form')]
            action['context'] = {
                'default_product_tmpl_id': self.id,
                'default_is_garment_bom': True,
                'default_run_id': self.selected_run_id.id,
                'default_product_id': False,
            }
            return action
        
        elif self.product_category == 'swatch':
            if not self.selected_swatch_number_id:
                raise ValidationError("Please select a Swatch # before creating a BOM.")
            
            action = self.env.ref('mrp.mrp_bom_form_action').read()[0]
            action['views'] = [(self.env.ref('mrp.mrp_bom_form_view').id, 'form')]
            action['context'] = {
                'default_product_tmpl_id': self.id,
                'default_is_swatch_bom': True,
                'default_swatch_number_id': self.selected_swatch_number_id.id,
                'default_product_id': False,
            }
            return action
        
        else:
            raise ValidationError("BOM creation is only supported for Garment and Swatch products.")
    
    
    
    def sync_yarn_stock(self):
        """Action to manually sync yarn stock from colors"""
        self.ensure_one()
        category = self.env.context.get('default_product_category') or self.product_category
        if category == 'yarn':    
            self._sync_yarn_stock_from_colors(self)
            
        return {'type': 'ir.actions.client', 'tag': 'reload'}
    
    # Menu action methods
    def action_view_all_products(self):
        action = self.env.ref('maeknit_inventory_customization.action_product_template_all')
        return action.read()[0]
    
    def action_view_yarn_products(self):
        action = self.env.ref('maeknit_inventory_customization.action_product_template_yarn')
        return action.read()[0]
    
    def action_view_garment_products(self):
        action = self.env.ref('maeknit_inventory_customization.action_product_template_garment')
        return action.read()[0]
    
    def action_view_swatch_products(self):
        action = self.env.ref('maeknit_inventory_customization.action_product_template_swatch')
        return action.read()[0]
    
    def action_view_services_products(self):
        action = self.env.ref('maeknit_inventory_customization.action_product_template_services')
        return action.read()[0]
    
    def action_view_misc_products(self):
        action = self.env.ref('maeknit_inventory_customization.action_product_template_misc')
        return action.read()[0]
    
    # Add the method to set default UOM based on product category
    def _get_default_uom(self):
        """Set default UOM based on product category"""
        # Get the UOM records
        kg_uom = self.env.ref('uom.product_uom_kgm', raise_if_not_found=False) or self.env['uom.uom'].search([('name', '=', 'Kg')], limit=1)
        unit_uom = self.env.ref('uom.product_uom_unit', raise_if_not_found=False) or self.env['uom.uom'].search([('name', '=', 'Units')], limit=1)
        
        # Default to kg for yarn, units for others
        category = self.env.context.get('default_product_category') or self.product_category
        
        if category == 'yarn':
            logging.info(f" Custom Code: Setting default UOM to Kg for yarn product: {self.name}")
            if self.name and not self.yarn_name:
                self.yarn_name = self.name
            return kg_uom.id if kg_uom else 12  # Default to Kg for yarn
        else:
            logging.info(f" Custom Code: Setting default UOM to Units for non-yarn product: {self.name}")
            return unit_uom.id if unit_uom else 1  # Default to Units for others
    
    def _update_vendor_info(self):
        """Update vendor info based on factory or vendor selection"""
        SupplierInfo = self.env['product.supplierinfo']
        
        # Determine the appropriate vendor based on product category
        vendor_partner = False
        if self.product_category in ['garment', 'swatch'] and self.factory_id:
            vendor_partner = self.factory_id
            logging.info(f" Custom Code: Using factory {vendor_partner.name} as vendor for {self.name}")
        elif self.product_category == 'yarn' and self.vendor_id:
            vendor_partner = self.vendor_id
            logging.info(f" Custom Code: Using vendor {vendor_partner.name} as vendor for {self.name}")
        
        # If we have a vendor, create or update the supplier info
        if vendor_partner:
            # Check if this vendor already exists
            existing = SupplierInfo.search([
                ('partner_id', '=', vendor_partner.id),
                ('product_tmpl_id', '=', self.id)
            ], limit=1)
            
            if not existing:
                # Create new supplier info
                SupplierInfo.create({
                    'partner_id': vendor_partner.id,
                    'product_tmpl_id': self.id,
                    'price': self.cost_price if self.cost_price else 0.0,
                    'delay': 1,  # Default lead time of 1 day
                })
                logging.info(f" Custom Code: Created vendor line for {self.name} with vendor {vendor_partner.name}")

    @api.constrains('name', 'brand_id', 'product_category')
    def _check_garment_duplicate(self):
        """Prevent duplicate garments with the same name and brand"""
        for record in self:
            if record.product_category == 'garment' and record.name and record.brand_id:
                # Search for duplicates with the same name and brand
                domain = [
                    ('id', '!=', record.id),  # Exclude current record
                    ('product_category', '=', 'garment'),
                    ('name', '=', record.name),
                    ('brand_id', '=', record.brand_id.id),
                    ('style_family', '=', record.style_family),
                ]
                
                duplicates = self.search(domain)
                
                if duplicates:
                    duplicate_names = ", ".join(duplicates.mapped('name'))
                    raise ValidationError((
                        "A garment with the name '%(name)s' already exists for brand '%(brand)s'. "
                        "Please use a different name or brand."
                    ) % {
                        'name': record.name,
                        'brand': record.brand_id.name
                    })

    def _get_default_routes(self, category):
        """Return a list of route IDs based on product category."""
        route_model = self.env['stock.route']
        route_map = {
            'mto': route_model.search([('name', '=', 'Replenish on Order (MTO)')], limit=1),
            'mfg_ny': route_model.search([('name', '=', 'Manufacture NY')], limit=1),
            'mfg_uk': route_model.search([('name', '=', 'Manufacture UK')], limit=1),
            'dropship': route_model.search([('name', '=', 'Dropship')], limit=1),
            'buy': route_model.search([('name', '=', 'Buy')], limit=1),
        }

        if category in ['garment', 'swatch', 'misc']:
            return [r.id for k, r in route_map.items() if k in ['mto', 'mfg_ny', 'mfg_uk', 'dropship'] and r]
        elif category == 'yarn':
            return [route_map['buy'].id] if route_map['buy'] else []
        return []
