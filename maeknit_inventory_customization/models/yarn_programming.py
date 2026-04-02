from odoo import models, fields, api

class YarnProgramming(models.Model):
    _name = 'yarn.programming'
    _description = 'Yarn Programming'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', ondelete='cascade')
    
    # Programming information
    machine = fields.Char(string='Machine')
    knit_structure = fields.Char(string='Knit Structure')
    yarn_ends = fields.Char(string='Yarn Ends')
    stitch_density = fields.Char(string='NP/Stitch Density')
    rows = fields.Char(string='Rows')
    needles = fields.Char(string='Needles')
    
    # Notes
    notes = fields.Text(string='Notes')
    
    # Display name for the record
    @api.depends('machine', 'knit_structure')
    def name_get(self):
        result = []
        for record in self:
            name = f"{record.machine or ''}"
            if record.knit_structure:
                name += f" - {record.knit_structure}"
            result.append((record.id, name))
        return result
