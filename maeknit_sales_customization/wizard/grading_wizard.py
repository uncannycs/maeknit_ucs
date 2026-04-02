from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

class GradingWizard(models.TransientModel):
    _name = 'grading.wizard'
    _description = 'Grading Wizard for Multiple Sizes and Colorways'
    
    bom_request_id = fields.Many2one('maeknit.bom.request', string='Source BOM Request', required=True, readonly=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', readonly=True)
    original_size_id = fields.Many2one('product.attribute.value', string='Size (Development)', readonly=True,
                                      help='Size from development BOM Request')
    original_colorway_id = fields.Many2one('product.attribute.value', string='Original Colorway (Development)', readonly=True,
                                          help='Colorway from development BOM Request')
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    grading_service_id = fields.Many2one('product.product', string='Grading Service', readonly=True)
    
    # Available values computed from product template
    available_colorway_ids = fields.Many2many('product.attribute.value', compute='_compute_available_colorway_ids', 
                                             string='Available Colorways')
    available_size_ids = fields.Many2many('product.attribute.value', compute='_compute_available_size_ids',
                                         string='Available Sizes')
    
    # Selection fields
    selected_colorway_ids = fields.Many2many('product.attribute.value', 'grading_wizard_colorway_rel',
                                            'wizard_id', 'colorway_id',
                                            string='Select Colorways for Grading',
                                            domain="[('id', 'in', available_colorway_ids)]")
    selected_size_ids = fields.Many2many('product.attribute.value', 'grading_wizard_size_rel',
                                        'wizard_id', 'size_id',
                                        string='Select Sizes for Grading',
                                        domain="[('id', 'in', available_size_ids)]")
    
    price_per_grade = fields.Float(string='Price per Grade', default=300.0,
                                   help='Price charged per size-colorway combination')
    
    @api.depends('product_tmpl_id')
    def _compute_available_colorway_ids(self):
        """Compute available colorways from style.colorway table"""
        for wizard in self:
            if wizard.product_tmpl_id:
                style_colorways = self.env['style.colorway'].search([
                    ('product_tmpl_id', '=', wizard.product_tmpl_id.id)
                ])
                colorway_ids = style_colorways.mapped('colorway_id')
                wizard.available_colorway_ids = colorway_ids | wizard.selected_colorway_ids
            else:
                wizard.available_colorway_ids = wizard.selected_colorway_ids
    
    @api.depends('product_tmpl_id')
    def _compute_available_size_ids(self):
        """Compute available sizes from product.template.attribute.line"""
        for wizard in self:
            if wizard.product_tmpl_id:
                size_attr = self.env['product.attribute'].search([('name', '=', 'Size')], limit=1)
                if size_attr:
                    attr_lines = self.env['product.template.attribute.line'].search([
                        ('product_tmpl_id', '=', wizard.product_tmpl_id.id),
                        ('attribute_id', '=', size_attr.id)
                    ])
                    size_ids = attr_lines.mapped('value_ids')
                    wizard.available_size_ids = size_ids | wizard.selected_size_ids
                else:
                    wizard.available_size_ids = wizard.selected_size_ids
            else:
                wizard.available_size_ids = wizard.selected_size_ids
    
    @api.model
    def default_get(self, fields_list):
        """Pre-populate wizard fields from context"""
        res = super().default_get(fields_list)
        
        bom_request_id = self.env.context.get('active_id')
        if bom_request_id:
            bom_request = self.env['maeknit.bom.request'].browse(bom_request_id)
            
            res['bom_request_id'] = bom_request.id
            res['product_tmpl_id'] = bom_request.product_tmpl_id.id
            res['partner_id'] = bom_request.partner_id.id
            res['original_size_id'] = bom_request.size_id.id if bom_request.size_id else False
            res['original_colorway_id'] = bom_request.colorway_id.id if bom_request.colorway_id else False
            
            # Find Grading Service
            grading_service = self.env['product.product'].search([
                ('name', '=', 'Grading Service'),
                ('type', '=', 'service')
            ], limit=1)
            res['grading_service_id'] = grading_service.id if grading_service else False
            
            # Pre-select original colorway and size
            if bom_request.colorway_id:
                res['selected_colorway_ids'] = [(6, 0, [bom_request.colorway_id.id])]
            if bom_request.size_id:
                res['selected_size_ids'] = [(6, 0, [bom_request.size_id.id])]
        
        return res
    
    def action_create_grading_boms(self):
        """Create Sales Order with grading service and size × colorway combinations"""
        self.ensure_one()
        
        if not self.selected_size_ids:
            raise ValidationError(_("Please select at least one size for grading."))
        if not self.selected_colorway_ids:
            raise ValidationError(_("Please select at least one colorway for grading."))
        
        # Ensure colorways are linked to product template
        self._ensure_colorways_linked_to_template()
        
        # Get grading service product
        if not self.grading_service_id:
            raise UserError(_("Grading Service product not found. Please create it first."))
        
        # Calculate total combinations and price
        total_combinations = len(self.selected_size_ids) * len(self.selected_colorway_ids)
        total_service_price = self.price_per_grade * total_combinations
        
        style_family = self.product_tmpl_id.style_family or 'unnamed-project'
        
        # Prepare Sales Order values
        sale_order_vals = {
            'partner_id': self.partner_id.id if self.partner_id else self.env.user.partner_id.id,
            'opportunity_id': self.bom_request_id.sale_order_id.lead_id.id if self.bom_request_id.sale_order_id.lead_id.id else False,
            'lead_id': self.bom_request_id.sale_order_id.lead_id.id if self.bom_request_id.sale_order_id.lead_id.id else False,
            'order_line': []
        }
        
        # Add grading service line
        sale_order_vals['order_line'].append((0, 0, {
            'product_id': self.grading_service_id.id,
            'product_uom_qty': 1.0,
            'price_unit': total_service_price,
            'rel_service': self.grading_service_id.id,
            'style_family': style_family,
        }))
        
        # Add garment lines for each size × colorway combination
        for size in self.selected_size_ids:
            for colorway in self.selected_colorway_ids:
                # Create notation like "(S) (Red)"
                size_notation = f"({size.name})"
                colorway_notation = f"({colorway.name})"
                
                sale_order_vals['order_line'].append((0, 0, {
                    'product_id': self.product_tmpl_id.product_variant_id.id,
                    'product_uom_qty': 1.0,
                    'revision': 'Revision 1',
                    'price_unit': 0,  # Price is on service line
                    'rel_service': self.grading_service_id.id,
                    'style_family': style_family,
                    'name': f"{size_notation} {colorway_notation}"
                }))
        
        # Create the Sales Order
        sale_order = self.env['sale.order'].create(sale_order_vals)
        
        logging.info(f"Created Sales Order {sale_order.name} with {total_combinations} grading combinations")
        
        # Return action to open the created Sales Order
        return {
            'type': 'ir.actions.act_window',
            'name': _('Grading Sales Order'),
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _ensure_colorways_linked_to_template(self):
        """Ensure all selected colorways are linked to the product template via style.colorway"""
        self.ensure_one()
        
        StyleColorway = self.env['style.colorway']
        
        for colorway in self.selected_colorway_ids:
            # Check if this colorway is already linked to the template
            existing = StyleColorway.search([
                ('product_tmpl_id', '=', self.product_tmpl_id.id),
                ('colorway_id', '=', colorway.id)
            ], limit=1)
            
            if not existing:
                # Create the style.colorway link
                try:
                    StyleColorway.create({
                        'product_tmpl_id': self.product_tmpl_id.id,
                        'colorway_id': colorway.id
                    })
                    logging.info(f"Linked colorway {colorway.name} to product {self.product_tmpl_id.name}")
                except Exception as e:
                    logging.warning(f"Could not link colorway {colorway.name}: {e}")
