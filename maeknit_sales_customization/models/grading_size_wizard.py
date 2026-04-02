from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import json
import logging

class GradingSizeWizard(models.TransientModel):
    _name = 'grading.size.wizard'
    _description = 'Grading Size Wizard'
    
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    sale_order_line_id = fields.Many2one('sale.order.line', string='Sale Order Line')
    product_id = fields.Many2one('product.product', string='Product', required=True,
                                 domain="[('type', '=', 'consu')]")
    sizes = fields.Char(string='Sizes (comma-separated)', required=True,
                       help='Enter sizes separated by commas, e.g., S, M, L, XL')
    price_per_grade = fields.Float(string='Price Per Grade', default=300.0)
    
    def action_add_sizes(self):
        """Add grading sizes and create variants"""
        self.ensure_one()
        
        if not self.sizes:
            raise ValidationError(_("Please enter at least one size."))
        
        # Parse sizes from comma-separated string
        size_list = [s.strip().upper() for s in self.sizes.split(',') if s.strip()]
        
        if not size_list:
            raise ValidationError(_("Please enter at least one valid size."))
        
        # Get or create Size attribute
        Attribute = self.env['product.attribute']
        AttributeValue = self.env['product.attribute.value']
        
        size_attr = Attribute.search([('name', '=', 'Size')], limit=1)
        if not size_attr:
            size_attr = Attribute.create({'name': 'Size', 'create_variant': 'always'})
        
        # Get base product template
        product_template = self.product_id.product_tmpl_id
        
        size_values = []
        for size_name in size_list:
            size_value = AttributeValue.search([
                ('attribute_id', '=', size_attr.id),
                ('name', '=', size_name)
            ], limit=1)
            
            if not size_value:
                size_value = AttributeValue.create({
                    'attribute_id': size_attr.id,
                    'name': size_name,
                })
            size_values.append(size_value)
        
        # Check if Size attribute is already on the product template
        attr_line = self.env['product.template.attribute.line'].search([
            ('product_tmpl_id', '=', product_template.id),
            ('attribute_id', '=', size_attr.id)
        ], limit=1)
        
        if not attr_line:
            attr_line = self.env['product.template.attribute.line'].create({
                'product_tmpl_id': product_template.id,
                'attribute_id': size_attr.id,
                'value_ids': [(6, 0, [sv.id for sv in size_values])],
            })
        else:
            existing_value_ids = attr_line.value_ids.ids
            new_value_ids = [sv.id for sv in size_values if sv.id not in existing_value_ids]
            if new_value_ids:
                attr_line.write({'value_ids': [(4, vid) for vid in new_value_ids]})
        
        # Get child CRM lead from the original line
        child_lead = self.sale_order_line_id.crm_child_lead_id if self.sale_order_line_id else None
        
        product_template._create_variant_ids()
        
        # Create SO lines for each size variant
        created_lines = []
        for size_value in size_values:
            # Find variant for this size
            variant = self.env['product.product'].search([
                ('product_tmpl_id', '=', product_template.id),
                ('product_template_attribute_value_ids.product_attribute_value_id', '=', size_value.id)
            ], limit=1)
            
            if variant:
                # Create SO line for this size variant
                line_vals = {
                    'order_id': self.sale_order_id.id,
                    'product_id': variant.id,
                    'product_uom_qty': 1,
                    'price_unit': 0.0,  # Grading size lines are $0
                    'rel_service': self.sale_order_id.x_rel_service_id.id if self.sale_order_id.x_rel_service_id else False,
                    'size': size_value.name,
                    'revision_status': 'none',
                }
                
                # Link to the same child CRM lead
                if child_lead:
                    line_vals['crm_child_lead_id'] = child_lead.id
                
                new_line = self.env['sale.order.line'].create(line_vals)
                created_lines.append(new_line)
        
        if child_lead:
            grading_data = {}
            if child_lead.x_grading_data:
                try:
                    grading_data = json.loads(child_lead.x_grading_data)
                except json.JSONDecodeError:
                    grading_data = {}
            
            if 'items' not in grading_data:
                grading_data['items'] = []
            if 'selectedItems' not in grading_data:
                grading_data['selectedItems'] = []
            
            grading_data['pricePerGrade'] = self.price_per_grade
            
            # Find or create item for this product
            item = None
            for existing_item in grading_data['items']:
                if existing_item.get('name') == product_template.name:
                    item = existing_item
                    break
            
            if not item:
                item = {
                    'id': product_template.id,
                    'name': product_template.name,
                    'styleCode': product_template.default_code or product_template.name,
                    'sizes': [],
                    'selected': True
                }
                grading_data['items'].append(item)
                grading_data['selectedItems'].append(product_template.id)
            
            # Update sizes
            item['sizes'] = size_list
            
            # Save grading data to child CRM lead
            child_lead.write({'x_grading_data': json.dumps(grading_data)})
        
        return {'type': 'ir.actions.act_window_close'}
