from odoo import models, fields, api

class MachineLibrary(models.Model):
    _name = 'machine.library'
    _description = 'Machine Library'
    _order = 'name'

    name = fields.Char(string='Machine Name', required=True)
    code = fields.Char(string='Machine Code')
    description = fields.Text(string='Description')
    manufacturer = fields.Char(string='Manufacturer')
    model = fields.Char(string='Model')
    active = fields.Boolean(default=True)
    
    # Relationships
    gauge_ids = fields.Many2many('gauge.library', string='Compatible Gauges')
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Machine name already exists!"),
    ]
