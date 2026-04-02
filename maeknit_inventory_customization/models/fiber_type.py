from odoo import models, fields, api
import re

class FiberType(models.Model):
    _name = 'fiber.type'
    _description = 'Fiber Type'
    _order = 'name'

    name = fields.Char(string='Fiber Type', required=True)
    value = fields.Char(string='Technical Value', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)
    
    # Add category field - nullable
    category_id = fields.Many2one('fiber.category', string='Category', ondelete='restrict')
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Fiber type already exists!"),
        ('value_uniq', 'unique (value)', "Fiber type value already exists!"),
    ]
    
    @api.model_create_multi
    def create(self, vals_list):
        """Capitalize fiber type names and generate technical values on creation"""
        for vals in vals_list:
            if vals.get('name'):
                vals['name'] = vals['name'].capitalize()
                # Generate value from name if not provided
                if not vals.get('value'):
                    vals['value'] = self._generate_value_from_name(vals['name'])
            elif vals.get('value') and not vals.get('name'):
                # If only value is provided, use it to generate a name
                vals['name'] = vals['value'].replace('_', ' ').capitalize()
        return super(FiberType, self).create(vals_list)
    
    def write(self, vals):
        """Capitalize fiber type names and update technical values on write"""
        for record in self:
            if vals.get('name') and not vals.get('value'):
                # If name is changed but value isn't, update value to match
                vals['value'] = self._generate_value_from_name(vals['name'])
            elif vals.get('value') and not vals.get('name'):
                # If value is changed but name isn't, update name to match
                vals['name'] = vals['value'].replace('_', ' ').capitalize()
            
            # Always capitalize name
            if vals.get('name'):
                vals['name'] = vals['name'].capitalize()
        
        return super(FiberType, self).write(vals)
    
    @api.onchange('name')
    def _onchange_name(self):
        """Generate value when name changes in the UI"""
        if self.name and not self.value:
            self.value = self._generate_value_from_name(self.name)
    
    @api.onchange('value')
    def _onchange_value(self):
        """Generate name when value changes in the UI"""
        if self.value and not self.name:
            self.name = self.value.replace('_', ' ').capitalize()
    
    def _generate_value_from_name(self, name):
        """Generate a technical value from a display name"""
        if not name:
            return ''
        # Convert to lowercase, replace spaces with underscores, remove special chars
        value = name.lower()
        value = re.sub(r'[^\w\s]', '', value)  # Remove special characters
        value = re.sub(r'\s+', '_', value)     # Replace spaces with underscores
        return value
