from odoo import models, fields, api

class FiberCategory(models.Model):
    _name = 'fiber.category'
    _description = 'Fiber Category'
    _order = 'name'

    name = fields.Char(string='Category Name', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)
    
    # This will be used in the future to show products in this category
    fiber_type_ids = fields.One2many('fiber.type', 'category_id', string='Fiber Types')
    fiber_type_count = fields.Integer(string='Fiber Types Count', compute='_compute_fiber_type_count')
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Fiber category already exists!"),
    ]
    
    @api.depends('fiber_type_ids')
    def _compute_fiber_type_count(self):
        for record in self:
            record.fiber_type_count = len(record.fiber_type_ids)
    
    @api.model_create_multi
    def create(self, vals_list):
        """Capitalize category names on creation"""
        for vals in vals_list:
            if vals.get('name'):
                vals['name'] = vals['name'].capitalize()
        return super(FiberCategory, self).create(vals_list)
    
    def write(self, vals):
        """Capitalize category names on update"""
        if vals.get('name'):
            vals['name'] = vals['name'].capitalize()
        return super(FiberCategory, self).write(vals)
    
    def action_view_fiber_types(self):
        """Open fiber types that belong to this category"""
        self.ensure_one()
        action = self.env.ref('maeknit_inventory_customization.action_fiber_type').read()[0]
        action['domain'] = [('category_id', '=', self.id)]
        action['context'] = {'default_category_id': self.id}
        return action
