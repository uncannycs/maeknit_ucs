from odoo import models, fields, api, Command, _
from odoo.osv import expression
import base64
import logging
import os
import json
import ast
from odoo.exceptions import ValidationError, UserError

class CrmLead(models.Model):
    _inherit = 'crm.lead'
    
    
    name = fields.Char(string="Project Name")
    
    x_service_revenues = fields.Char(string="Service Revenues", help="JSON data for revenue per service")
    season_drop_date = fields.Date(string="Season / Drop Date", required=False)
    x_onboarding_data = fields.Char(string="Onboarding Data", help="JSON data for onboarding information")
    x_gemini_notes = fields.Text(string="Gemini Notes", help="Notes from Gemini")
    x_include_development_in_quote = fields.Boolean(string="Include Development in Quote", default=False)
    x_include_production_in_quote = fields.Boolean(string="Include Production in Quote", default=False)
    x_include_swatch_in_quote = fields.Boolean(string="Include Swatch Service in Quote", default=False)
    x_include_grading_in_quote = fields.Boolean(string="Include Grading Service in Quote", default=False)
    x_include_reverse_in_quote = fields.Boolean(string="Include Reverse Engineering Service in Quote", default=False)
    x_created_products = fields.Char(string="Created Products", help="JSON data for created products")
    x_child_style_name = fields.Char(string='Style Name')
    x_selected_child_leads = fields.Text(string='Selected Child Leads', default='[]')
    x_development_prices = fields.Char(string="Development Prices", help="JSON data for development prices per item")
    x_swatch_data = fields.Char(string="Swatch Data", help="JSON data for swatch items and colorways")
    x_grading_data = fields.Char(string="Grading Data", help="JSON data for grading items and sizes")
    x_reverse_data = fields.Char(string="Reverse Engineering Data", help="JSON data for reverse engineering items and prices")

    company_id = fields.Many2one('res.company', 'Lab', index=True, default=lambda self: self.env.company)

    # Override partner_id to make it required
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, 
                            help='Linked partner (optional). Usually created when converting the lead.')

    parent_id = fields.Many2one('crm.lead', string="Parent Lead")
    child_ids = fields.One2many('crm.lead', 'parent_id', string="Child Opportunities")
    
    product_ids = fields.Many2many("crm.lead.product", string="Products")
    
    style_family = fields.Char(
        string="Style Family",
        readonly=True,
        copy=False,
        help="Unique identifier generated from client initials + sequence (e.g., AB-0001)",
    )
    expected_revenue = fields.Monetary(
        compute="_compute_expected_revenue", readonly=False, store=True, recursive=True
    )
    
    x_project_type = fields.Selection([
        ('style', 'Style'),
        ('collection', 'Collection')
    ], string="Project Type", default='collection', required=True)
    
    x_service_revenues_dict = fields.Properties(
        string="Service Revenues Dict",
        compute='_compute_x_service_revenues_dict',
        inverse='_inverse_x_service_revenues_dict',
        store=False # Not stored, computed on the fly
    )

    stage_domain = fields.Char(
        string='Stage Domain',
        compute='_compute_stage_domain',
        store=False,
        compute_sudo=True
    )

    stage_id = fields.Many2one(
        'crm.stage',
        string='Stage',
        ondelete='restrict',
        tracking=True,
        index=True,
        group_expand='_read_group_stage_ids',
        copy=False,
        domain="[('id', 'in', eval(stage_domain or '[]'))]"
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        return res
    
    @api.depends('x_project_type', 'write_date')
    def _compute_stage_domain(self):

        for lead in self:
            project_type = lead.x_project_type or 'collection'
            
            # Build domain based on project type
            domain = ['|', ('x_stage_type', '=', project_type),
                        ('x_stage_type', '=', 'both')]

            stages = self.env['crm.stage'].search(domain)
            lead.stage_domain = str(stages.ids)

    @api.onchange('x_project_type')
    def _onchange_project_type(self):
        self._compute_stage_domain()
        return {'domain': {'stage_id': self._get_stage_domain()}}

    def _get_stage_domain(self):
        project_type = self.x_project_type or 'collection'

        domain = ['|', ('x_stage_type', '=', project_type),
                    ('x_stage_type', '=', 'both')]

        return domain
    
    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """
        Override to filter stages in kanban/statusbar based on project_type.
        Shows stages already in use OR stages matching the current project types.
        """
        # Determine which project types are in the current view
        leads = self.search(domain) if domain else self.env['crm.lead']
        project_types = set(leads.mapped('x_project_type')) if leads else set()

        # Build stage type filter: match specific project types + 'both'
        stage_type_filter = [('x_stage_type', '=', 'both')]
        for pt in project_types:
            if pt:
                stage_type_filter.append(('x_stage_type', '=', pt))

        if len(stage_type_filter) > 1:
            stage_type_domain = ['|'] * (len(stage_type_filter) - 1) + stage_type_filter
        else:
            stage_type_domain = stage_type_filter

        # OR logic: stages already in use OR stages matching the type filter
        # This ensures new/empty stages still appear as kanban columns
        search_domain = ['|', ('id', 'in', stages.ids)] + stage_type_domain

        return stages.search(search_domain)

    @api.depends('x_service_revenues')
    def _compute_x_service_revenues_dict(self):
        for lead in self:
            try:
                lead.x_service_revenues_dict = json.loads(lead.x_service_revenues or "{}")
            except json.JSONDecodeError:
                lead.x_service_revenues_dict = {}

    def _inverse_x_service_revenues_dict(self):
        for lead in self:
            lead.x_service_revenues = json.dumps(lead.x_service_revenues_dict)

    @api.model
    def _generate_style_family(self, partner_name):
        """
        Generate a unique style_family identifier from client initials + sequence.
        e.g., "Company, John Doe" → "JD-0001"
        """
        initials = ""
        person = ""

        if partner_name:
            if "," in partner_name:
                _company, person = [x.strip() for x in partner_name.split(",", 1)]
            else:
                person = partner_name.strip()

            if person:
                parts = person.split()
                if len(parts) > 1:
                    initials = (parts[0][0] + parts[-1][0]).upper()
                else:
                    initials = parts[0][0].upper()

        next_number = self.env['ir.sequence'].next_by_code('crm.lead.style.family')
        if not next_number:
            logging.error("Sequence 'crm.lead.style.family' not found.")
            return f"{initials}-ERROR"

        formatted_number = str(next_number).zfill(4)
        return f"{initials}-{formatted_number}"

    @api.constrains('partner_id', 'company_id')
    def _check_partner_id(self):
        """
        Validate that partner_id is set
        """
        for record in self:
            if not record.partner_id:
                raise ValidationError(_('Client is required. Please select a client or brand.'))

    @api.depends("child_ids.expected_revenue")
    def _compute_expected_revenue(self):
        """
        Expected revenue is the sum of the child expected revenue
        """
        for record in self:
            if record.child_ids:
                record.expected_revenue = sum(
                    record.child_ids.mapped("expected_revenue")
                )
            else:
                record.expected_revenue = record.expected_revenue
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'season_drop_date' in vals and vals.get('season_drop_date') == '':
                vals['season_drop_date'] = False
            if 'x_development_prices' in vals and not vals['x_development_prices']:
                vals['x_development_prices'] = "{}"
            if 'x_project_type' not in vals:
                vals['x_project_type'] = 'collection'
            # Always auto-generate style_family from the single sequence
            if not vals.get('style_family'):
                partner_name = ''
                if vals.get('partner_id'):
                    partner = self.env['res.partner'].browse(vals['partner_id'])
                    partner_name = partner.name or ''
                vals['style_family'] = self._generate_style_family(partner_name)
            # Keep x_child_style_name in sync with style_family
            vals['x_child_style_name'] = vals['style_family']
        return super(CrmLead, self).create(vals_list)


    def write(self, vals):
        if 'season_drop_date' in vals and vals.get('season_drop_date') == '':
            vals['season_drop_date'] = False
        if 'x_development_prices' in vals and not vals['x_development_prices']:
            vals['x_development_prices'] = "{}"
        result = super(CrmLead, self).write(vals)

        # Sync name to linked garment/swatch products via style_family (avoid infinite loop)
        # Only sync from child/style leads — collection name is independent
        if 'name' in vals and not self.env.context.get('_syncing_product_name'):
            for lead in self:
                if lead.x_project_type == 'collection' or not lead.style_family:
                    continue
                linked_products = self.env['product.template'].search([
                    ('style_family', '=', lead.style_family),
                    ('product_category', 'in', ['garment', 'swatch']),
                ])
                if linked_products:
                    linked_products.with_context(_syncing_product_name=True).write({
                        'name': vals['name']
                    })

        return result
    
    def _check_existing_quotation(self):
        """
        Check if there's already a quotation for the same CRM lead with the same quote options
        """
        # Get current quote settings
        quote_settings = {
            'development': self.x_include_development_in_quote,
            'production': self.x_include_production_in_quote,
            'swatch': self.x_include_swatch_in_quote,
            'grading': self.x_include_grading_in_quote,
            'reverse': self.x_include_reverse_in_quote,
        }
        
        
        # Find which service is selected for quote
        selected_service = None
        for service, is_selected in quote_settings.items():
            if is_selected:
                selected_service = service
                break
        
        if not selected_service:
            return None
                    
        # Search for existing sale orders from this lead
        if not self.id:
            return None

        logging.info("Checking for existing orders for lead ID: %s", self.id)        
        existing_orders = self.env['sale.order'].search([
            ('opportunity_id', '=', self.id),
            ('state', 'in', ['draft', 'sent', 'sale'])  # Active quotations/orders
        ])
        
        # Check if any existing order has the same quote configuration
        for order in existing_orders:
            # Check order lines to determine what was quoted
            order_services = set()
            
            for line in order.order_line:
                # Now related_service is a Many2one, so check its name
                if line.rel_service:
                    service_name = line.rel_service.name
                    if 'Development' in service_name:
                        order_services.add('development')
                    elif 'Production' in service_name:
                        order_services.add('production')
                    elif 'Swatch' in service_name:
                        order_services.add('swatch')
                    elif 'Grading' in service_name:
                        order_services.add('grading')
                    elif 'Reverse' in service_name:
                        order_services.add('reverse')
            
            # If this order has the same service type, it's a duplicate
            if selected_service in order_services:
                return order
                
        return None
    
    def action_sale_quotations_new(self):
        """
        Override to create products before creating a quotation and check for duplicates
        """
        
        # If we're already in the process of creating a quotation, just call parent
        if self.env.context.get('bypass_quote_check'):
            return super(CrmLead, self).action_sale_quotations_new()
        
        # Check if any quote options are selected
        if not (self.x_include_development_in_quote or 
                self.x_include_production_in_quote or 
                self.x_include_swatch_in_quote or 
                self.x_include_grading_in_quote or
                self.x_include_reverse_in_quote):
            return {
                'name': _('Confirm Quote Creation'),
                'type': 'ir.actions.act_window',
                'res_model': 'crm.lead.quote.confirm',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_lead_id': self.id,
                    'default_warning_message': _('No quote options are selected. Are you sure you want to create a quotation without any selected services?'),
                }
            }
        
        existing_order = self._check_existing_quotation()
        try:
            if existing_order:
                current_products = set(existing_order.order_line.mapped('product_id').ids)

                new_products = self._update_existing_products(existing_order.order_line.mapped('product_id'))
                logging.info("New products: %s", new_products)
                garment_product = new_products.get('garment')
                dev_service_product = new_products.get('dev_service')

                style_family = self.style_family or 'unnamed-project'
                # Add missing line(s)
                if garment_product:
                    logging.info("Adding garment product %s to existing quotation %s", garment_product, existing_order.id)
                    existing_order.order_line.append({
                        'order_id': existing_order.id,
                        'product_id': garment_product.product_variant_id.id,
                        'product_uom_qty': 1.0,
                        'price_unit': 0,
                        'sample': 'Sample 1',
                        'rel_service': dev_service_product.product_variant_id.id if dev_service_product else False,
                        'style_family': garment_product.style_family,
                    })

                # Return the Sales Order window
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Quotation'),
                    'res_model': 'sale.order',
                    'view_mode': 'form',
                    'res_id': existing_order.id,
                    'target': 'current'
                }
        except Exception as e:
            logging.error("Error updating existing quotation: %s", str(e))
        # Create the products based on selected options
        created_products = self._create_default_products()
        # Store created products for use in quotation lines
        if created_products:
            self.x_created_products = json.dumps({
                'development': created_products.get('development', {}).id if created_products.get('development') else False,
                'swatch_service': created_products.get('swatch_service', {}).id if created_products.get('swatch_service') else False,
                'garment': [p.id for p in created_products.get('garment', [])] if isinstance(created_products.get('garment'), list) else (
                    [created_products['garment'].id] if created_products.get('garment') else []
                ),
                'dev_swatch': created_products.get('dev_swatch', {}).id if created_products.get('dev_swatch') else False,
                'swatch': [p.id for p in created_products.get('swatch', [])] if created_products.get('swatch') else [],
                'production': created_products.get('production', {}).id if created_products.get('production') else False,
                'grading': created_products.get('grading', {}).id if created_products.get('grading') else False,
                'reverse': created_products.get('reverse', {}).id if created_products.get('reverse') else False,
                'graded_garments': [p.id for p in created_products.get('graded_garments', [])] if created_products.get('graded_garments') else [],
            })
        
        # Get the order lines we want to include
        order_lines = []
        
        # Add lines for newly created products
        created_product_lines = self._get_created_product_lines()
        if created_product_lines:
            order_lines.extend([Command.create(line) for line in created_product_lines])
        
        # Call the parent method to get the action
        action = super(CrmLead, self).action_sale_quotations_new()
        
        if 'context' in action:
            if isinstance(action['context'], str):
                try:
                    action['context'] = ast.literal_eval(action['context'])
                except Exception as e:
                    action['context'] = {}

            action['context'] = dict(action['context'])  # Make a copy
            
            # Ensure active_id is set in the context
            action['context']['active_id'] = self.id
            action['context']['active_ids'] = [self.id]
            action['context']['active_model'] = 'crm.lead'
            
            # Update the action's context to include our order lines
            if order_lines:
                action['context']['default_order_line'] = order_lines
        else:
            # If no context exists, create one with the necessary values
            action['context'] = {
                'active_id': self.id,
                'active_ids': [self.id],
                'active_model': 'crm.lead',
            }
            if order_lines:
                action['context']['default_order_line'] = order_lines
                
        return action
    
    def _prepare_opportunity_quotation_context(self):
        """
        Override the data to include the sale order lines for the quotation
        """
        logging.info(" Custom Code:=== _prepare_opportunity_quotation_context CALLED for lead: %s ===", self.name)
        res = super(CrmLead, self)._prepare_opportunity_quotation_context()
        
        # Add lines for newly created products
        created_product_lines = self._get_created_product_lines()
        logging.info("Created product lines: %s", created_product_lines)
        
        # Combine all lines
        all_lines = created_product_lines
        logging.info("All quotation lines: %s", all_lines)
        
        if all_lines:
            res["default_order_line"] = [Command.create(line) for line in all_lines]
            logging.info(" Custom Code:Added %s order lines to quotation context", len(all_lines))
        
        return res
    
    def _get_created_product_lines(self):
        """
        Get order lines for products that were just created during this quotation process
        """
        lines = []
        
        if not self.x_created_products:
            return lines
            
        try:
            created_products = json.loads(self.x_created_products)
            logging.info("Created products data: %s", created_products)
            # Get product templates
            ProductTemplate = self.env['product.template']
            ProductProduct = self.env['product.product']

            
            # Get style family - use child style names if this is a collection
            project_name = self.name or "Unnamed Project"
            style_family = self.style_family or 'unnamed-project'
            logging.info("Project name: %s, Style family: %s", project_name, style_family)

            # Search for existing service products
            dev_service_product = ProductTemplate.search([
                ('name', '=', 'Development Service'),
                ('type', '=', 'service')
            ], limit=1)
            
            logging.info("dev_service_product: %s", dev_service_product)
            
            swatch_service_product = ProductTemplate.search([
                ('name', '=', 'Swatch Service'),
                ('type', '=', 'service')
            ], limit=1)
            logging.info("Swatch service product: %s", swatch_service_product)

            
            grading_service_product = ProductTemplate.search([
                ('name', '=', 'Grading Service'),
                ('type', '=', 'service')
            ], limit=1)
            logging.info("Grading service product: %s", grading_service_product)

            
            # reverse_service_product = ProductTemplate.search([
            #     ('name', '=', 'Reverse Engineering Service'),
            #     ('type', '=', 'service')
            # ], limit=1)
            # 
            # 
            #  logging.info("Reverse engineering service product: %s", reverse_service_product)
            
            # Get service revenues
            dev_revenue = self._get_service_revenue_by_tag("Development")
            swatch_revenue = self._get_service_revenue_by_tag("Swatch Service")
            production_revenue = self._get_service_revenue_by_tag("Production")
            grading_revenue = self._get_service_revenue_by_tag("Grading")
            reverse_revenue = self._get_service_revenue_by_tag("Reverse Engineering")
            logging.info("Service revenues: Dev=%s, Swatch=%s, Production=%s, Grading=%s, Reverse=%s", 
                dev_revenue, swatch_revenue, production_revenue, grading_revenue, reverse_revenue)

            development_prices = {}
            if self.x_development_prices:
                try:
                    development_prices = json.loads(self.x_development_prices)
                    logging.info("Parsed development prices: %s", development_prices)
                except json.JSONDecodeError:
                    logging.error("Failed to parse x_development_prices: %s", self.x_development_prices)
                    development_prices = {}
            
            # If Development service is included, add lines for garments
            if self.x_include_development_in_quote:
                logging.info("Including development in quote.")
                garment_ids = created_products.get('garment', [])
                logging.info("Development garment IDs: %s", garment_ids)

                garment_products = ProductTemplate
                if garment_ids:
                    garment_products = ProductTemplate.browse(garment_ids)
                
                if len(garment_products) > 0:
                    for garment_product in reversed(garment_products):
                        logging.info("Processing development garment: %s", garment_product.name)
                        style_family = garment_product.style_family or style_family
                        garment_price = float(development_prices.get(str(garment_product.parent_project_id.id), 0.0))
                        final_price_unit = garment_price if garment_price > 0 else (dev_revenue or 2000)
                        
                        if garment_product and garment_product.product_variant_id:
                            ''' 
                            Consolidation
                            lines.append({
                                'product_id': dev_service_product.product_variant_id.id,
                                'product_uom_qty': 1.0,
                                'price_unit': final_price_unit,
                                'rel_service': dev_service_product.product_variant_id.id,
                                'style_family': style_family,
                            })
                            '''
                            lines.append({
                                'product_id': garment_product.product_variant_id.id,
                                'product_uom_qty': 1.0,
                                'price_unit': final_price_unit,
                                'sample': 'Sample 1',
                                'rel_service': dev_service_product.product_variant_id.id,
                                'style_family': style_family,
                            })
            
            # If Swatch service is included, add lines for garments
            if self.x_include_swatch_in_quote:
                if swatch_service_product:
                    # Get swatch data to determine how to structure the lines
                    swatch_data = {}
                    if self.x_swatch_data:
                        try:
                            swatch_data = json.loads(self.x_swatch_data)
                        except json.JSONDecodeError:
                            logging.error("Failed to parse x_swatch_data: %s", self.x_swatch_data)
                    swatch_items = swatch_data.get('items', [])
                    swatch_service_price = swatch_data.get('servicePrice', [])
                    logging.info("Swatch items: %s", swatch_items)
                    logging.info("Swatch service price: %s", swatch_service_price)
                
                    # If we have swatch data items, create structured lines
                    if swatch_items:
                        lines.append({
                                        'product_id': swatch_service_product.product_variant_id.id,
                                        'product_uom_qty': 1.0,
                                        'price_unit': swatch_service_price or 250,
                                        'rel_service': swatch_service_product.product_variant_id.id,
                                    })
                        for swatch_item in swatch_items:
                            logging.info("Processing swatch item: %s", swatch_item)
                            if swatch_item.get('tempId') in swatch_data.get('selectedItems', []):
                                swatch_ids = created_products.get('swatch', [])
                                logging.info("Swatch IDs: %s", swatch_ids)
                                swatch_products = ProductTemplate
                                if swatch_ids:
                                    swatch_products = ProductTemplate.browse(swatch_ids)
                                logging.info("Swatch products: %s", swatch_products)
                                matched_product = None
                                for swatch_product in swatch_products:
                                    logging.info("swatch_product. name : %s", swatch_product.name)
                                    logging.info("swatch_product. name : %s", swatch_item.get('name'))

                                    style_family = swatch_product.style_family or style_family
                                    if swatch_product.name == swatch_item.get('name'):
                                        matched_product = swatch_product
                                        break
                                logging.info("Matched product: %s", matched_product)
                                if matched_product:
                                    lines.append({
                                        'product_id': matched_product.product_variant_id.id,
                                        'product_uom_qty': 1.0,
                                        'revision': 'Revision 1',
                                        'rel_service': swatch_service_product.product_variant_id.id,
                                        'style_family': swatch_item.get('styleCode', style_family),
                                        'name': matched_product.name,
                                    })

                    else:                        
                        swatch_ids = created_products.get('swatch', [])
                        swatch_products = ProductTemplate
                        if swatch_ids:
                            lines.append({
                                        'product_id': swatch_service_product.product_variant_id.id,
                                        'product_uom_qty': 1.0,
                                        'price_unit': swatch_service_price or 250,
                                        'rel_service': swatch_service_product.product_variant_id.id,
                                    })
                            swatch_products = ProductTemplate.browse(swatch_ids)
                            for swatch_product in swatch_products:
                                if swatch_product and swatch_product.product_variant_id:
                                    lines.append({
                                        'product_id': swatch_product.product_variant_id.id,
                                        'product_uom_qty': 1.0,
                                        'revision': 'Revision 1',
                                        'price_unit': swatch_product.list_price or 0.0,
                                        'rel_service': swatch_service_product.product_variant_id.id,
                                        'style_family': style_family,
                                    })
            
            # Reverse Engineering is obsolete
            '''
            if self.x_include_reverse_in_quote:
                garment_ids = created_products.get('garment', [])
                garment_products = ProductTemplate
                if garment_ids:
                    garment_products = ProductTemplate.browse(garment_ids)
                
                if len(garment_products) > 0:
                    for garment_product in reversed(garment_products):
                        style_family = garment_product.style_family or style_family
                        garment_price = float(development_prices.get(str(garment_product.parent_project_id.id), 0.0))
                        final_price_unit = garment_price if garment_price > 0 else (reverse_revenue or 2000)
                        
                        if garment_product and garment_product.product_variant_id:
                            lines.append({
                                'product_id': reverse_service_product.product_variant_id.id,
                                'product_uom_qty': 1.0,
                                'price_unit': final_price_unit,
                                'rel_service': reverse_service_product.product_variant_id.id,
                                'style_family': style_family,
                            })
                            
                            lines.append({
                                'product_id': garment_product.product_variant_id.id,
                                'sample': 'Sample 1',
                                'product_uom_qty': 1.0,
                                'rel_service': reverse_service_product.product_variant_id.id,
                                'style_family': style_family,
                            })
            '''
            # If Grading service is included, add lines for garments
            if self.x_include_grading_in_quote and grading_service_product:
                # Get grading data to create individual lines for each size
                grading_data = {}
                if self.x_grading_data:
                    try:
                        grading_data = json.loads(self.x_grading_data)
                    except json.JSONDecodeError:
                        logging.error("Failed to parse x_grading_data: %s", self.x_grading_data)
                grading_items = grading_data.get('items', [])
                price_per_grade = grading_data.get('pricePerGrade', 300)  
                selectedItems = grading_data.get('selectedItems', [])
                # Get or create the 'Size' attribute
                for item in reversed(grading_items):
                    logging.info("Grading item: %s", item)
                    child_name = item.get('name', f"{project_name} - Substyle")
                    child_style_family = item.get('styleCode', style_family)
                    garment_category = self._get_or_create_category('Garment')
                    garment_product = self._create_product_template(
                        name=child_name,
                        categ_id=garment_category.id,
                        product_category='garment',
                        type='consu',
                        style_family=child_style_family,
                        lead=self.id,
                        brand_id=self.partner_id
                    )
                    
                    if item.get('id') in selectedItems:
                        logging.info("Processing grading item: %s", item)
                        sizes = item.get('sizes', [])
                        multi = 0
                        for size_str in sizes:
                            multi+=1
                        total_service_price = price_per_grade * multi
                               
                        lines.append({
                            'product_id': grading_service_product.product_variant_id.id,
                            'product_uom_qty': 1.0,
                            'price_unit': total_service_price,
                            'rel_service': grading_service_product.product_variant_id.id,
                            'style_family': child_style_family,
                        })                 
                        MrpBom = self.env['mrp.bom']
                        colorway_value = self._get_or_create_attribute_value('Colorway', 'N/A')
                        original_product_template = garment_product
                        for size_str in sizes:
                            cleaned_size = size_str.strip()
                            if not cleaned_size:
                                continue
                            size_value = self._get_or_create_attribute_value('Size', cleaned_size)
                            variant = False
                            variant = MrpBom._find_or_create_specific_garment_variant(
                                original_product_template,
                                colorway_value,
                                size_value
                            )
                            logging.info("Found/created variant: %s", variant)
                            variant = variant or original_product_template.product_variant_id
                            variant_id = variant.id if variant else False
                            if not variant_id:
                                logging.warning(
                                    "Unable to assign a variant for size %s on template %s",
                                    cleaned_size, original_product_template.name
                                )
                            lines.append({
                                'product_id': variant_id,
                                'product_uom_qty': 1.0,
                                'revision': 'Revision 1',
                                'price_unit': 0,  # Use the price per grade
                                'rel_service': grading_service_product.product_variant_id.id,
                                'style_family': original_product_template.style_family,
                                'name': variant.name + '(' + cleaned_size + ')',
                                'size': cleaned_size
                            })
                        
            # Add production service if it exists
            '''
            production_data = created_products.get('production')
            logging.info("Production data: %s", production_data)
            if production_data:
                if isinstance(production_data, int):
                    prod_product = ProductTemplate.browse(production_data)
                elif isinstance(production_data, str):
                    prod_product = ProductTemplate.search([
                        ('name', '=', production_data),
                        ('type', '=', 'service')
                    ], limit=1)
                else:
                    prod_product = self.env['product.template']
                
                if prod_product and prod_product.product_variant_id:
                    lines.append({
                        'product_id': prod_product.product_variant_id.id,
                        'product_uom_qty': 1.0,
                        'price_unit': prod_product.list_price or 0.0,
                        'rel_service': prod_product.product_variant_id.id,
                        'style_family': style_family,
                    })
        ''' 
            if self.x_include_production_in_quote:
                prod_product = ProductTemplate.search([
                    ('name', '=', 'Production Service'),
                    ('type', '=', 'service')
                ], limit=1)    
                lines.append({
                                'product_id': prod_product.product_variant_id.id,
                                'product_uom_qty': 1.0,
                                'price_unit': prod_product.list_price or 0.0,
                                'rel_service': prod_product.product_variant_id.id,
                                'style_family': style_family,
                            })     
        except Exception as e:
            logging.error("Error getting created product lines: %s", e)
        default_route_id = self._get_default_manufacturing_route_id()
        if default_route_id:
            logging.info("Applying default manufacturing route %s to %s lines for lead %s", 
                         default_route_id, len(lines), self.name)
            for line in lines:
                logging.info("Assigning route to line: %s", line)
                line.setdefault('route_id', default_route_id)
        return lines
    
    def _get_default_manufacturing_route_id(self):
        """
        Return Manufacture NY or Manufacture UK route based on the user's current company.
        """
        company = self.company_id or self.env.user.company_id
        if not company:
            return False
        company_name = (company.name or '').lower()
        route_name = 'Manufacture UK' if 'uk' in company_name else 'Manufacture NY'
        logging.info("Default route check (lead company=%s user=%s): trying route %s",
                     company.name or company.id, self.env.user.login, route_name)
        route = self.env['stock.route'].search([('name', '=', route_name)], limit=1)
        if not route:
            logging.warning("Default manufacturing route '%s' not found for company %s", route_name, company.name or company.id)
            return False
        logging.info("Default manufacturing route %s (%s) resolved for company %s", route.name, route.id, company.name or company.id)
        return route.id
    def _update_existing_products(self, existing_products):
        """
        Returns the product templates that should be added to the quotation.
        No product creation happens here. Only selects existing products.
        """
        ProductTemplate = self.env['product.template']
        result = {}

        logging.info("Updating existing products for Lead ID %s", self.id)
        logging.info("Existing products: %s", existing_products) 
        # Development Service
        if self.x_include_development_in_quote:
            dev = ProductTemplate.search([
                ('name', '=', 'Development Service'),
                ('type', '=', 'service')
            ], limit=1)
            logging.info("Development Service included: %s", bool(dev))
            if dev:
                result['development'] = dev

        # Grading Service
        if self.x_include_grading_in_quote:
            grading = ProductTemplate.search([
                ('name', '=', 'Grading Service'),
                ('type', '=', 'service')
            ], limit=1)
            logging.info("Grading Service included: %s", bool(grading))
            if grading:
                result['grading'] = grading

        # Garment Products (Style OR Collection children)
        if self.x_include_development_in_quote:
            result['garment'] = []

            logging.info("Checking garment products for project type: %s", self.x_project_type)

            # COLLECTION
            if self.x_project_type == 'collection' and self.child_ids:
                selected_child_ids = []
                if self.x_selected_child_leads:
                    logging.info("x_selected_child_leads: %s", self.x_selected_child_leads)
                    try:
                        selected_child_ids = json.loads(self.x_selected_child_leads)
                    except json.JSONDecodeError:
                        logging.error("Failed to parse x_selected_child_leads: %s", self.x_selected_child_leads)

                logging.info("Selected child IDs: %s", selected_child_ids)

                for child in self.child_ids:
                    try:
                        logging.info("Evaluating child lead %s (ID: %s)", child.name, child.id)
                        logging.info('child.x_child_style_name: %s', child.x_child_style_name)  

                        if child.id not in selected_child_ids:
                            logging.info("Child %s NOT selected, skipping.", child.name)
                            continue

                        # Prepare values
                        child_name = child.name or f"{project_name} - Substyle"
                        child_style_family = child.style_family or style_family

                        garment_category = self._get_or_create_category('Garment')

                        # Check if garment already exists
                        existing_garment = self.env['product.template'].search([
                            ('product_category', '=', 'garment'),
                            ('style_family', '=', child_style_family),
                        ], limit=1)

                        if existing_garment:
                            logging.info(
                                "Already exists → Garment for child %s (ID %s) = Product %s",
                                child.name, child.id, existing_garment.id
                            )
                            continue

                        # CREATE only if not existing
                        logging.info(
                            "Creating garment product for child %s (ID %s)",
                            child.name, child.id
                        )
                        
                        garment_product = self._create_product_template(
                            name=child_name,
                            categ_id=garment_category.id,
                            product_category='garment',
                            type='consu',
                            style_family=child_style_family,
                            lead=child.id,
                            brand_id=self.partner_id
                        )

                        logging.info(
                            "Garment CREATED → child %s (ID %s) → Product %s",
                            child.name, child.id, garment_product.id
                        )

                        result['garment'].append(garment_product)

                    except Exception as e:
                        logging.error("Error evaluating child lead %s: %s", child.name, str(e))
            else:
                logging.info("Single style project — garment product ID: %s",
                            self.x_created_garment_product_id.id if self.x_created_garment_product_id else None)

                if self.x_created_garment_product_id:
                    result['garment'] = [self.x_created_garment_product_id]

        # Production Service
        if self.x_include_production_in_quote:
            prod = ProductTemplate.search([
                ('name', 'ilike', 'Production Service'),
                ('type', '=', 'service')
            ], limit=1)

            logging.info("Production Service included: %s", bool(prod))

            if prod:
                result['production'] = prod

        # Swatches (selected only)
        if self.x_include_swatch_in_quote and self.x_swatch_data:
            result['swatch'] = []
            try:
                swatch_data = json.loads(self.x_swatch_data)
            except json.JSONDecodeError:
                logging.error("Failed to parse swatch JSON data.")
                swatch_data = {}

            selected_ids = swatch_data.get('selectedItems', [])
            items = swatch_data.get('items', [])

            logging.info("Selected swatch IDs: %s", selected_ids)

            for item in items:
                if item.get('tempId') in selected_ids:
                    product_id = item.get('productId')
                    logging.info("Checking swatch tempId %s → productId %s",
                                item.get('tempId'), product_id)

                    if product_id:
                        p = ProductTemplate.browse(product_id)
                        if p.exists():
                            logging.info("Adding existing swatch product ID: %s", p.id)
                            result['swatch'].append(p)
                        else:
                            logging.warning("Swatch product ID %s not found", product_id)

        logging.info("Final result of _update_existing_products: %s", result)

        return result

    
    def _create_default_products(self):
        """
        Create the default product templates based on selected options
        """
        logging.info(" Custom Code:=== Creating default products for lead: %s", self.name)
        
        if not self.name:
            logging.info("Lead has no name, using default")
            project_name = "Unnamed Project"
        else:
            project_name = self.name
        
        # Get or create product categories
        garment_category = self._get_or_create_category('Garment')
        swatch_category = self._get_or_create_category('Swatch')
        service_category = self._get_or_create_category('Services')
        
        style_family = self.style_family or 'unnamed-project'
        logging.info("Project name: %s, Style family: %s", project_name, style_family)
        result = {}
        ProductTemplate = self.env['product.template']

        # Create products based on selected options
        if self.x_include_development_in_quote or self.x_include_reverse_in_quote or self.x_include_grading_in_quote:
            # Create service products
            if self.x_include_development_in_quote:
                dev_service_product = ProductTemplate.search([
                    ('name', '=', 'Development Service'),
                    ('type', '=', 'service')
                ], limit=1)
                result['development'] = dev_service_product

            if self.x_include_grading_in_quote:
                grading_service_product = ProductTemplate.search([
                    ('name', '=', 'Grading Service'),
                    ('type', '=', 'service')
                ], limit=1)
                result['grading'] = grading_service_product

            if self.x_project_type == 'collection' and self.child_ids:
                selected_child_ids = []
                # Child Leads are selected for Garment Development
                if self.x_selected_child_leads:
                    try:
                        selected_child_ids = json.loads(self.x_selected_child_leads)
                    except json.JSONDecodeError:
                        logging.error("Failed to parse x_selected_child_leads: %s", self.x_selected_child_leads)
                        selected_child_ids = []
                logging.info("Selected child IDs for collection: %s", selected_child_ids)
                result['garment'] = []
                for child in self.child_ids:
                    if child.id in selected_child_ids:
                        logging.info("Creating garment product for child lead: %s (ID: %s)", child.name, child.id)
                        if self.x_include_development_in_quote:
                            child_name = child.name or f"{project_name} - Substyle"
                            child_style_family = child.style_family or style_family
                            garment_product = self._create_product_template(
                                name=child_name,
                                categ_id=garment_category.id,
                                product_category='garment',
                                type='consu',
                                style_family=child_style_family,
                                lead=child.id,
                                brand_id=self.partner_id
                            )
                            result['garment'].append(garment_product)
            else:
                # Default behavior for 'style' or if no children for collection
                if self.x_include_development_in_quote:
                    garment_product = self._create_product_template(
                        name=project_name,
                        categ_id=garment_category.id,
                        product_category='garment',
                        type='consu',
                        style_family=style_family,
                        lead=self.id,
                        brand_id=self.partner_id
                    )
                    result['garment'] = [garment_product]
        
        if self.x_include_production_in_quote:
            # Create Production Service product
            prod_service_product = self._create_product_template(
                name=f"{project_name} - Production Service",
                categ_id=service_category.id,
                product_category='services',
                type='service',
                style_family=style_family,
                lead=self.id,
                brand_id=self.partner_id
            )
            result['production'] = prod_service_product
            
        if self.x_include_swatch_in_quote:
            swatch_service_product = ProductTemplate.search([
                ('name', '=', 'Swatch Service'),
                ('type', '=', 'service')
            ], limit=1)
            result['swatch_service'] = swatch_service_product
            
            swatch_data = {}
            if self.x_swatch_data:
                try:
                    swatch_data = json.loads(self.x_swatch_data)
                except json.JSONDecodeError:
                    logging.error("Failed to parse x_swatch_data: %s", self.x_swatch_data)
            swatch_items = swatch_data.get('items', []) 
            created_swatches = []           
            if swatch_items:
                for swatch_item in swatch_items:
                    if swatch_item.get('tempId') in swatch_data.get('selectedItems', []):
                        style_code = swatch_item.get('styleCode', style_family)
                        swatch_name = swatch_item.get('name', 'Swatch')  # Just the base name, no project suffix

                        # Check first — use swatch_name, not swatch_name + project
                        existing_swatch = ProductTemplate.search([
                            ('name', '=', swatch_name),
                            ('categ_id', '=', swatch_category.id),
                            ('style_family', '=', style_code),
                        ], limit=1)

                        if existing_swatch:
                            logging.info("Swatch product already exists: %s (ID: %s)", existing_swatch.name, existing_swatch.id)
                            swatch_product = existing_swatch
                        else:
                            # Create the product using consistent name
                            swatch_product = self._create_product_template(
                                name=swatch_name,
                                categ_id=swatch_category.id,
                                product_category='swatch',
                                type='consu',
                                style_family=style_code,
                                lead=self.id,
                                brand_id=self.partner_id
                            )
                            created_swatches.append(swatch_product)

                        result['swatch'] = result.get('swatch', []) + [swatch_product]

            if created_swatches:
                result['swatch'] = created_swatches
        return result
    
    def _get_no_of_swatches(self):
        """
        Get the number of swatches for this opportunity
        """
        if not self.x_onboarding_data:
            return 0
        try:
            onboarding_data = json.loads(self.x_onboarding_data)
            return onboarding_data.get('swatchPackage', {}).get('numberOfSwatches', 0)
        except Exception as e:
            logging.error("Failed to parse x_onboarding_data or fetch swatch count: %s", e)
            return 0
    
    def _get_service_revenue_by_tag(self, tag_name="Development"):
        if not self.x_service_revenues:
            return None

        try:
            revenue_dict = json.loads(self.x_service_revenues)
            Tag = self.env['crm.tag']
            
            # Find the tag with the translated name
            tag = Tag.search([('name', 'ilike', tag_name)], limit=1)
            
            if tag:
                tag_id_str = str(tag.id)
                revenue = revenue_dict.get(tag_id_str)
                logging.info("Revenue for tag '%s' (ID %s): %s", tag_name, tag_id_str, revenue)
                return revenue
            else:
                logging.info("Tag with name '%s' not found", tag_name)
                return None
        except Exception as e:
            logging.error("Failed to parse x_service_revenues or fetch tag: %s", e)
            return None

    def _get_products(self):
        """
        Get the products for this opportunity and it's children
        """
        products = self.product_ids
        for child in self.child_ids:
            products |= child._get_products()
        return products

    def _get_or_create_category(self, category_name):
        """
        Get or create a product category
        """
        ProductCategory = self.env['product.category']
        category = ProductCategory.search([('name', '=', category_name)], limit=1)
        if not category:
            category = ProductCategory.create({
                'name': category_name,
            })
            logging.info("Created new product category: %s", category_name)
        return category

    def _get_or_create_attribute_value(self, attribute_name, value_name):
        """
        Ensure an attribute value exists for the given attribute name and value.
        """
        if not attribute_name or not value_name:
            return False

        Attribute = self.env['product.attribute']
        AttributeValue = self.env['product.attribute.value']

        attribute = Attribute.search([('name', '=', attribute_name)], limit=1)
        if not attribute:
            attribute = Attribute.create({'name': attribute_name})
            logging.info("Created missing product attribute: %s", attribute_name)

        value = AttributeValue.search([
            ('attribute_id', '=', attribute.id),
            ('name', '=', value_name),
        ], limit=1)

        if not value:
            value = AttributeValue.create({
                'attribute_id': attribute.id,
                'name': value_name,
            })
            logging.info("Created missing attribute value '%s' for attribute %s", value_name, attribute_name)

        return value
    
    def _create_product_template(self, name, categ_id, product_category, type='consu', style_family=None, lead=None, brand_id=None):
        """
        Create a product template with the given parameters
        """
        logging.info("Creating/finding product template: %s", name)
        ProductTemplate = self.env['product.template']
        
        # Check if product template already exists
        product_domain = [
            ('name', '=', name),
            ('categ_id', '=', categ_id),
            ('style_family', '=', style_family),
        ]
        if brand_id:
            product_domain.append(('brand_id', '=', brand_id.id))
        if lead:
            product_domain.append(('parent_project_id', '=', lead))

        existing_product = ProductTemplate.search(product_domain, limit=1)

        if existing_product:
            logging.info("Product already exists: %s (ID: %s)", existing_product.name, existing_product.id)
            return existing_product

        if brand_id:
            fallback_domain = [
                ('name', '=', name),
                ('categ_id', '=', categ_id),
                ('style_family', '=', style_family),
                ('brand_id', '=', brand_id.id),
            ]
            fallback_product = ProductTemplate.search(fallback_domain, limit=1)
            if fallback_product:
                logging.info("Found fallback existing product without matching lead: %s (ID: %s)", fallback_product.name, fallback_product.id)
                return fallback_product
        
        # Set default prices based on product type
        list_price = 0
        standard_price = 0
        
        # Prepare product values
        product_vals = {
            'name': name,
            'categ_id': categ_id,
            'product_category': product_category,
            'parent_project_id': lead,
            'style_family': style_family,
            'brand_id': brand_id.id if brand_id else False,
            'type': type,
            'sale_ok': True,
            'purchase_ok': True,
            'list_price': list_price,
            'standard_price': standard_price,
            'description': f"Product created from CRM Lead: {name}",
        }
        
        # Create the product template
        new_product = ProductTemplate.create(product_vals)
        logging.info("Created new product template: %s (ID: %s)", new_product.name, new_product.id)
        
        # Force commit to ensure product is available
        self.env.cr.commit()
        
        return new_product

    @api.onchange('partner_id')
    def _clear_name_on_partner_change(self):
        self.name = False

    @api.model
    def get_next_child_style_sequence(self, partner_name):
        """
        Generates initials from the person's name and combines them
        with a global sequence to form the next child style code.
        Expected formats:
            "Company, First Last"
            "First Last"
            "Company" (no initials)
        """
        initials = ""
        company = ""
        person = ""

        if partner_name:
            logging.info("Partner name: %s", partner_name)

            # Split into company + person when comma exists
            if "," in partner_name:
                company, person = [x.strip() for x in partner_name.split(",", 1)]
            else:
                # No comma; treat the whole value as 'person'
                person = partner_name.strip()

            # Compute initials only from the person part
            if person:
                parts = person.split()
                if len(parts) > 1:
                    initials = (parts[0][0] + parts[-1][0]).upper()
                else:
                    initials = parts[0][0].upper()
        
        # Get the next sequence number
        sequence_code = 'crm.lead.child.style'
        next_number = self.env['ir.sequence'].next_by_code(sequence_code)
        
        if not next_number:
            logging.error("Sequence with code '%s' not found or not configured.", sequence_code)
            return f"{initials}-ERROR"
            
        # Format the number with leading zeros (e.g., 0001)
        formatted_number = str(next_number).zfill(4)
        
        return f"{initials}-{formatted_number}"
    
    @api.model
    def get_next_swatch_style_sequence(self):
        """
        Generates the next style name for a child opportunity based on client initials and a global sequence.
        """
        initials = "SW"    
        # Get the next sequence number
        sequence_code = 'crm.lead.swatch.style'
        next_number = self.env['ir.sequence'].next_by_code(sequence_code)
        
        if not next_number:
            logging.error("Sequence with code '%s' not found or not configured.", sequence_code)
            return f"{initials}-ERROR"
            
        # Format the number with leading zeros (e.g., 0001)
        formatted_number = str(next_number).zfill(4)
        
        return f"{initials}-{formatted_number}"

    # ===== Currency and Display Methods =====

    def get_currency_symbol(self):
        """
        Get the currency symbol for this lead's company
        """
        self.ensure_one()
        if self.company_id and self.company_id.currency_id:
            return self.company_id.currency_id.symbol or '$'
        return '$'

    # ===== Production Grid Methods =====

    def get_production_grid_data(self):
        """
        Get all data needed for the production grid:
        - Products (from Products Tab via parent_project_id)
        - Sizes and Colorways for each product
        - Existing grid data (quantities and prices)
        """
        self.ensure_one()

        currency_symbol = '$'
        if self.company_id and self.company_id.currency_id:
            currency_symbol = self.company_id.currency_id.symbol or '$'

        # Find products via parent_project_id - only templates explicitly linked to this lead
        # For collections: include products linked to child leads AND directly to the collection
        ProductTemplate = self.env['product.template']
        if self.x_project_type == 'collection' and self.child_ids:
            search_ids = list(self.child_ids.ids) + [self.id]
            products = ProductTemplate.search([
                ('parent_project_id', 'in', search_ids),
            ])
        else:
            products = ProductTemplate.search([
                ('parent_project_id', '=', self.id),
            ])

        if not products:
            return {
                'products': [],
                'has_products': False,
                'grid_data': {},
                'currency_symbol': currency_symbol
            }

        # Build product data with variants
        product_data = []
        all_colorways = set()
        all_sizes = set()

        for product in products:
            # Get sizes and colorways for this product
            StyleSize = self.env['style.size']
            StyleColorway = self.env['style.colorway']

            sizes = StyleSize.search([
                ('product_tmpl_id', '=', product.id),
                ('active', '=', True)
            ]).mapped('size_id')

            colorways = StyleColorway.search([
                ('product_tmpl_id', '=', product.id),
                ('active', '=', True)
            ]).mapped('colorway_id')

            # Collect all unique colorways and sizes for grid columns/rows
            all_colorways.update(colorways.mapped('name'))
            all_sizes.update(sizes.mapped('name'))

            # If no variants, still show the product with simple qty/price
            if not sizes and not colorways:
                product_data.append({
                    'id': product.id,
                    'name': product.name,
                    'has_variants': False,
                    'sizes': [],
                    'colorways': [],
                    'default_price': product.list_price or 0.0
                })
            else:
                product_data.append({
                    'id': product.id,
                    'name': product.name,
                    'has_variants': True,
                    'sizes': [{'id': s.id, 'name': s.name} for s in sizes],
                    'colorways': [{'id': c.id, 'name': c.name} for c in colorways],
                    'default_price': product.list_price or 0.0
                })

        # Get existing grid data
        GridLine = self.env['crm.lead.production.grid']
        existing_lines = GridLine.search([('lead_id', '=', self.id)])

        grid_data = {}
        for line in existing_lines:
            key = f"{line.product_id.id}_{line.size_id.id or 0}_{line.colorway_id.id or 0}"
            grid_data[key] = {
                'quantity': line.quantity,
                'price': line.unit_price
            }

        return {
            'products': product_data,
            'has_products': True,
            'all_colorways': sorted(list(all_colorways)),
            'all_sizes': sorted(list(all_sizes)),
            'grid_data': grid_data,
            'currency_symbol': currency_symbol
        }

    def save_production_grid(self, grid_data):
        """
        Save grid data to database
        grid_data format: {
            'product_id_size_id_colorway_id': {'quantity': X, 'price': Y}
        }
        """
        self.ensure_one()
        GridLine = self.env['crm.lead.production.grid']

        for key, data in grid_data.items():
            parts = key.split('_')
            if len(parts) != 3:
                continue

            product_id = int(parts[0])
            size_id = int(parts[1]) if parts[1] != '0' else None
            colorway_id = int(parts[2]) if parts[2] != '0' else None

            # Get or create grid line
            line = GridLine.get_or_create_grid_line(
                self.id, product_id, size_id, colorway_id
            )

            # Update quantity and price
            line.write({
                'quantity': data.get('quantity', 0.0),
                'unit_price': data.get('price', 0.0)
            })

        return True

    def generate_production_prices_from_cost(self):
        """
        Populate the unit_price in every production grid row for each product
        template from that template's sales_price field.
        All rows (colorway-header and size+colorway cells) are updated so
        every variant of that template gets the same price.
        """
        self.ensure_one()
        GridLine = self.env['crm.lead.production.grid']

        products = GridLine.search([('lead_id', '=', self.id)]).mapped('product_id')
        for product in products:
            price = product.sales_price
            if not price:
                continue
            GridLine.search([
                ('lead_id', '=', self.id),
                ('product_id', '=', product.id),
            ]).write({'unit_price': price})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Prices Updated',
                'message': 'Unit prices have been set from product sales price.',
                'type': 'success',
            }
        }

    def create_products_for_production(self):
        """
        Pull products from the Products Tab and link them to the production grid.
        - Reads product_ids (Products Tab) to get product templates
        - Sets parent_project_id on those templates so they appear in the production grid
        - Falls back to creating garment products from child leads if Products Tab is empty
        """
        self.ensure_one()

        templates_to_link = {}  # {tmpl_id: lead_id to set as parent_project_id}

        # --- Step 1: collect templates from Products Tab ---
        leads_to_check = [self]
        if self.x_project_type == 'collection' and self.child_ids:
            leads_to_check += list(self.child_ids)

        for lead in leads_to_check:
            for lp in lead.product_ids:
                if lp.product_id:
                    tmpl = lp.product_id.product_tmpl_id
                    if tmpl and tmpl.id not in templates_to_link:
                        # For collection, prefer to link to the specific child lead;
                        # fall back to the parent collection lead.
                        if lead != self:
                            templates_to_link[tmpl.id] = lead.id
                        else:
                            templates_to_link[tmpl.id] = self.id

        # --- Step 2: fallback – create garment templates from child leads ---
        if not templates_to_link:
            garment_category = self._get_or_create_category('Garment')
            if self.x_project_type == 'collection' and self.child_ids:
                for child in self.child_ids:
                    if not child.style_family:
                        continue
                    existing = self.env['product.template'].search([
                        ('parent_project_id', '=', child.id),
                        ('product_category', '=', 'garment')
                    ], limit=1)
                    if not existing:
                        existing = self._create_product_template(
                            name=child.name,
                            categ_id=garment_category.id,
                            product_category='garment',
                            type='consu',
                            style_family=child.style_family,
                            lead=child.id,
                            brand_id=self.partner_id
                        )
                    if existing:
                        templates_to_link[existing.id] = child.id
            else:
                # Style project fallback
                if not self.style_family:
                    return False
                existing = self.env['product.template'].search([
                    ('parent_project_id', '=', self.id),
                    ('product_category', '=', 'garment')
                ], limit=1)
                if not existing:
                    self._create_default_products()
                    existing = self.env['product.template'].search([
                        ('parent_project_id', '=', self.id),
                        ('product_category', '=', 'garment')
                    ], limit=1)
                if existing:
                    templates_to_link[existing.id] = self.id

        # --- Step 3: set parent_project_id on templates that don't have it yet ---
        for tmpl_id, lead_id in templates_to_link.items():
            tmpl = self.env['product.template'].browse(tmpl_id)
            if not tmpl.parent_project_id:
                tmpl.write({'parent_project_id': lead_id})

        return True

    def add_product_to_production(self, product_tmpl_id):
        """
        Manually add a product template to the production grid.
        Links it to this lead via parent_project_id and reloads grid data.
        """
        self.ensure_one()
        tmpl = self.env['product.template'].browse(product_tmpl_id)
        if not tmpl.exists():
            return False
        # Always link to this lead (overwrites any existing parent_project_id)
        tmpl.write({'parent_project_id': self.id})
        # Return fresh grid data so the frontend can re-render
        return self.get_production_grid_data()

    def remove_product_from_production(self, product_tmpl_id):
        """
        Remove a product template from the production grid for this lead.
        Clears parent_project_id if it points to this lead or any child lead.
        """
        self.ensure_one()
        all_lead_ids = [self.id] + list(self.child_ids.ids)
        tmpl = self.env['product.template'].browse(product_tmpl_id)
        if tmpl.exists() and tmpl.parent_project_id.id in all_lead_ids:
            tmpl.write({'parent_project_id': False})
        # Delete all grid lines for this product across this lead and child leads
        self.env['crm.lead.production.grid'].search([
            ('lead_id', 'in', all_lead_ids),
            ('product_id', '=', product_tmpl_id),
        ]).unlink()
        return self.get_production_grid_data()

    @api.model
    def search_products_for_production(self, lead_id, search_term):
        """
        Search all product templates with no domain restrictions.
        Returns up to 20 matching templates.
        """
        domain = []
        if search_term:
            domain.append(('name', 'ilike', search_term))
        products = self.env['product.template'].search(domain, limit=20)
        return [{'id': p.id, 'name': p.name} for p in products]

    def generate_quote_from_production_grid(self):
        """
        Generate sale order from production grid data
        Only includes lines with quantity > 0
        """
        self.ensure_one()

        # Get grid lines with quantity > 0
        GridLine = self.env['crm.lead.production.grid']
        lines_to_quote = GridLine.get_lines_with_quantity(self.id)

        if not lines_to_quote:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Items to Quote',
                    'message': 'Please enter quantities greater than 0 in the production grid.',
                    'type': 'warning',
                }
            }

        # Create sale order
        SaleOrder = self.env['sale.order']

        # Collect unique style families from the grid lines
        style_families = set()
        for line in lines_to_quote:
            if line.product_id.style_family:
                style_families.add(line.product_id.style_family)

        # Find Production Service product for the service field
        production_service = self.env['product.product'].search([
            ('name', '=', 'Production Service')
        ], limit=1)

        order_vals = {
            'partner_id': self.partner_id.id,
            'opportunity_id': self.id,
            'lead_id': self.id,
            'campaign_id': self.campaign_id.id,
            'medium_id': self.medium_id.id,
            'source_id': self.source_id.id,
            'team_id': self.team_id.id,
            'user_id': self.user_id.id,
            'x_rel_services': 'production',
            'x_quoted_style_families': ', '.join(sorted(style_families)) if style_families else False,
            'x_rel_service_id': production_service.id if production_service else False,
        }

        order = SaleOrder.create(order_vals)

        # Add order lines — one line per grid cell (quantity > 0).
        # Use the specific size+colorway variant; create it (+ BOM) if missing.
        SaleOrderLine = self.env['sale.order.line']
        MrpBom = self.env['mrp.bom']

        # Resolve Production Service product for BOM rel_service
        production_service_product = self.env['product.product'].search([
            ('name', '=', 'Production Service')
        ], limit=1)

        for line in lines_to_quote:
            # Resolve the specific product.product variant for this size+colorway
            if line.size_id and line.colorway_id:
                variant = MrpBom._find_or_create_specific_garment_variant(
                    line.product_id, line.colorway_id, line.size_id
                )
                # Ensure a BOM exists for this combination with customer + service
                existing_bom = MrpBom.search([
                    ('product_tmpl_id', '=', line.product_id.id),
                    ('colorway_id', '=', line.colorway_id.id),
                    ('size_id', '=', line.size_id.id),
                ], limit=1)
                if not existing_bom:
                    MrpBom.create({
                        'product_tmpl_id': line.product_id.id,
                        'colorway_id': line.colorway_id.id,
                        'size_id': line.size_id.id,
                        'partner_id': self.partner_id.id if self.partner_id else False,
                        'rel_service': production_service_product.id if production_service_product else False,
                    })
                else:
                    # Update existing BOM with customer and service if not already set
                    update_vals = {}
                    if not existing_bom.partner_id and self.partner_id:
                        update_vals['partner_id'] = self.partner_id.id
                    if not existing_bom.rel_service and production_service_product:
                        update_vals['rel_service'] = production_service_product.id
                    if update_vals:
                        existing_bom.write(update_vals)
            else:
                variant = line.product_id.product_variant_id

            product_id = variant.id if variant else line.product_id.product_variant_id.id

            # Price: prefer the colorway-header row price, then cell price, then cost
            price = line.unit_price
            if line.colorway_id:
                price_record = GridLine.search([
                    ('lead_id', '=', self.id),
                    ('product_id', '=', line.product_id.id),
                    ('colorway_id', '=', line.colorway_id.id),
                    ('size_id', '=', False)
                ], limit=1)
                if price_record and price_record.unit_price:
                    price = price_record.unit_price
            if not price:
                price = line.product_id.sales_price or 0.0

            SaleOrderLine.with_context(skip_crm_child_lead=True).create({
                'order_id': order.id,
                'product_id': product_id,
                'product_uom_qty': line.quantity,
                'price_unit': price,
                'name': self._get_variant_description(line),
                'style_family': line.product_id.style_family or False,
                'size': line.size_id.name if line.size_id else False,
                'colorway': line.colorway_id.name if line.colorway_id else False,
            })

        # Return action to open the created order
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quotation',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def _find_or_create_variant(self, product_template, size_id, colorway_id):
        """Find or create a specific product variant for a size+colorway combination."""
        if size_id and colorway_id:
            return self.env['mrp.bom']._find_or_create_specific_garment_variant(
                product_template, colorway_id, size_id
            )
        return product_template.product_variant_id

    def _get_variant_description(self, grid_line):
        """
        Generate description for sale order line from grid line
        """
        parts = [grid_line.product_id.name]

        if grid_line.size_id:
            parts.append(f"Size: {grid_line.size_id.name}")

        if grid_line.colorway_id:
            parts.append(f"Colorway: {grid_line.colorway_id.name}")

        return " - ".join(parts)

    def action_open_variant_wizard(self, product_id):
        """
        Open the variant creation wizard for a product
        """
        self.ensure_one()

        product = self.env['product.template'].browse(product_id)
        if not product.exists():
            return False

        wizard = self.env['crm.lead.variant.wizard'].create({
            'product_id': product.id,
            'lead_id': self.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Add Product Variants',
            'res_model': 'crm.lead.variant.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }
class CRMLeadProduct(models.Model):
    _name = "crm.lead.product"
    _description = "A product associated with a Lead"

    product_id = fields.Many2one("product.product", required=True)
    quantity = fields.Float()
    price = fields.Float(readonly=False, compute="_compute_values", store=True)
    cost = fields.Float(readonly=False, compute="_compute_values", store=True)

    @api.depends("product_id")
    def _compute_values(self):
        """
        Default in the product's values
        """
        for record in self:
            record.price = record.product_id.list_price
            record.cost = record.product_id.standard_price


class CrmLeadExistingQuoteWarning(models.TransientModel):
    _name = 'crm.lead.existing.quote.warning'
    _description = 'CRM Lead Existing Quote Warning'

    lead_id = fields.Many2one('crm.lead', string='Lead', required=True)
    existing_order_id = fields.Many2one('sale.order', string='Existing Order', required=True)
    warning_message = fields.Text(string='Warning Message', readonly=True)

    def action_go_to_existing(self):
        """
        Go to the existing quotation
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Existing Quotation',
            'res_model': 'sale.order',
            'res_id': self.existing_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
        
    def action_cancel(self):
        """
        Cancel creating a quotation
        """
        return {'type': 'ir.actions.act_window_close'}

