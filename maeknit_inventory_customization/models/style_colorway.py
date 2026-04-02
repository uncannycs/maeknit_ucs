from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

class StyleColorway(models.Model):
    """
    Style-specific colorway management table.
    This allows each style (product template) to have its own set of colorways
    that are unique to that style, while still maintaining the global colorway library.
    """
    _name = 'style.colorway'
    _description = 'Style-Specific Colorway'
    _rec_name = 'colorway_name'
    _order = 'product_tmpl_id, colorway_name'

    # Foreign key relationships
    product_tmpl_id = fields.Many2one(
        'product.template', 
        string='Style', 
        required=True, 
        ondelete='cascade',
        help="The style/product template this colorway belongs to"
    )
    
    colorway_id = fields.Many2one(
        'product.attribute.value', 
        string='Global Colorway', 
        domain="[('attribute_id.name', '=', 'Colorway')]",
        required=True,
        help="Reference to the global colorway from product.attribute.value"
    )
    
    # Display fields
    colorway_name = fields.Char(
        string='Colorway Name', 
        related='colorway_id.name', 
        help="Name of the colorway for easy searching and display"
    )
    
    style_name = fields.Char(
        string='Style Name', 
        related='product_tmpl_id.name', 
        help="Name of the style for easy reference"
    )
    
    # Metadata fields
    active = fields.Boolean(default=True, help="Set to false to archive this colorway for the style")
    sequence = fields.Integer(default=10, help="Sequence for ordering colorways within a style")
    notes = fields.Text(string='Notes', help="Additional notes about this colorway for this specific style")
    
    # Tracking fields
    created_date = fields.Datetime(string='Created Date', default=fields.Datetime.now)
    created_by_bom = fields.Boolean(
        string='Created by BOM', 
        default=False,
        help="True if this colorway was automatically created when a BOM was made"
    )
    
    # Usage tracking
    bom_count = fields.Integer(
        string='BOM Count', 
        compute='_compute_bom_count',
        help="Number of BOMs using this colorway for this style"
    )
    
    @api.depends('product_tmpl_id', 'colorway_id')
    def _compute_bom_count(self):
        """Count how many BOMs use this colorway for this style"""
        for record in self:
            if record.product_tmpl_id and record.colorway_id:
                bom_count = self.env['mrp.bom'].search_count([
                    ('product_tmpl_id', '=', record.product_tmpl_id.id),
                    ('colorway_id', '=', record.colorway_id.id)
                ])
                record.bom_count = bom_count
            else:
                record.bom_count = 0
    
    @api.constrains('product_tmpl_id', 'colorway_id')
    def _check_unique_colorway_per_style(self):
        """Ensure each colorway is unique per style"""
        for record in self:
            if record.product_tmpl_id and record.colorway_id:
                duplicate = self.search([
                    ('id', '!=', record.id),
                    ('product_tmpl_id', '=', record.product_tmpl_id.id),
                    ('colorway_id', '=', record.colorway_id.id)
                ], limit=1)
                
                if duplicate:
                    raise ValidationError(
                        f"Colorway '{record.colorway_name}' already exists for style '{record.style_name}'. "
                        "Each colorway can only be added once per style."
                    )
    
    @api.model
    def get_or_create_style_colorway(self, product_tmpl_id, colorway_id):
        """
        Get existing or create new style-specific colorway.
        This is used when BOMs are created to automatically add colorways to styles.
        """
        existing = self.search([
            ('product_tmpl_id', '=', product_tmpl_id),
            ('colorway_id', '=', colorway_id)
        ], limit=1)
        
        if existing:
            return existing
        
        # Create new style colorway
        return self.create({
            'product_tmpl_id': product_tmpl_id,
            'colorway_id': colorway_id,
            'created_by_bom': True
        })
    
    @api.model
    def get_colorways_for_style(self, product_tmpl_id):
        """
        Get all colorways available for a specific style.
        Returns the colorway_ids that can be used in BOMs for this style.
        """
        style_colorways = self.search([
            ('product_tmpl_id', '=', product_tmpl_id),
            ('active', '=', True)
        ])
        return style_colorways.mapped('colorway_id')
    
    def name_get(self):
        """Custom name display: Style - Colorway"""
        result = []
        for record in self:
            name = f"{record.style_name} - {record.colorway_name}"
            result.append((record.id, name))
        return result
    
    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Enhanced search to find by style name or colorway name"""
        if args is None:
            args = []
        
        if name:
            # Search by colorway name or style name
            domain = ['|', 
                     ('colorway_name', operator, name),
                     ('style_name', operator, name)]
            records = self.search(domain + args, limit=limit)
            return records.name_get()
        
        return super().name_search(name, args, operator, limit)
