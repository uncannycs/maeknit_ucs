from odoo import models, fields, api

class StitchLibrary(models.Model):
    _name = 'stitch.library'
    _description = 'Stitch Library'
    _order = 'name'

    name = fields.Char(string='Stitch Name', required=True)
    code = fields.Char(string='Stitch Code')
    body_part = fields.Char(string='Body Part', required=True, help="E.g., Body, Sleeve, Collar, Cuff, Hem, Pocket, etc.")
    
    # Keep the selection field for backward compatibility but make it optional
    stitch_type_selection = fields.Selection([
        ('jersey', 'Jersey'),
        ('interlock', 'Interlock'),
        ('rib', 'Rib'),
        ('2x1_rib', '2x1 Rib'),
        ('2x2_rib', '2x2 Rib'),
        ('other', 'Other')
    ], string='Legacy Stitch Type', required=False)
    
    # Use this as the main field
    stitch_type = fields.Char(string='Stitch Type', required=True, help="E.g., Jersey, Interlock, Rib, Cable, Moss, etc.")
    
    gauge_ids = fields.Many2many('gauge.library', string='Compatible Gauges')
    machine_ids = fields.Many2many('machine.library', string='Compatible Machines')
    
    description = fields.Text(string='Description')
    notes = fields.Text(string='Technical Notes')
    active = fields.Boolean(default=True)
    
    # For visual reference
    image = fields.Binary(string='Stitch Image', attachment=True)
    image_filename = fields.Char(string='Image Filename')
    
    # Technical specifications
    stitch_density = fields.Char(string='Stitch Density')
    tension = fields.Char(string='Tension')
    
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    
    @api.depends('name', 'stitch_type', 'body_part')
    def _compute_display_name(self):
        for record in self:
            parts = []
            if record.name:
                parts.append(record.name)
            if record.stitch_type:
                parts.append(record.stitch_type)
            if record.body_part:
                parts.append(f"({record.body_part})")
            
            record.display_name = " ".join(parts)
    
    @api.onchange('stitch_type')
    def _onchange_stitch_type(self):
        """Update legacy stitch_type_selection field when stitch_type changes"""
        if self.stitch_type:
            stitch_type_lower = self.stitch_type.lower()
            if 'jersey' in stitch_type_lower:
                self.stitch_type_selection = 'jersey'
            elif 'interlock' in stitch_type_lower:
                self.stitch_type_selection = 'interlock'
            elif '2x1' in stitch_type_lower and 'rib' in stitch_type_lower:
                self.stitch_type_selection = '2x1_rib'
            elif '2x2' in stitch_type_lower and 'rib' in stitch_type_lower:
                self.stitch_type_selection = '2x2_rib'
            elif 'rib' in stitch_type_lower:
                self.stitch_type_selection = 'rib'
            else:
                self.stitch_type_selection = 'other'
    
    @api.onchange('stitch_type_selection')
    def _onchange_stitch_type_selection(self):
        """Update stitch_type field when stitch_type_selection changes"""
        if self.stitch_type_selection and not self.stitch_type:
            selection_labels = dict([
                ('jersey', 'Jersey'),
                ('interlock', 'Interlock'),
                ('rib', 'Rib'),
                ('2x1_rib', '2x1 Rib'),
                ('2x2_rib', '2x2 Rib'),
                ('other', 'Other')
            ])
            self.stitch_type = selection_labels.get(self.stitch_type_selection, '')
    
    @api.model_create_multi
    def create(self, vals_list):
        """Ensure stitch_type and stitch_type_selection are in sync"""
        for vals in vals_list:
            # Case 1: stitch_type → stitch_type_selection
            if 'stitch_type' in vals and 'stitch_type_selection' not in vals:
                stitch_type_lower = vals['stitch_type'].lower()
                if 'jersey' in stitch_type_lower:
                    vals['stitch_type_selection'] = 'jersey'
                elif 'interlock' in stitch_type_lower:
                    vals['stitch_type_selection'] = 'interlock'
                elif '2x1' in stitch_type_lower and 'rib' in stitch_type_lower:
                    vals['stitch_type_selection'] = '2x1_rib'
                elif '2x2' in stitch_type_lower and 'rib' in stitch_type_lower:
                    vals['stitch_type_selection'] = '2x2_rib'
                elif 'rib' in stitch_type_lower:
                    vals['stitch_type_selection'] = 'rib'
                else:
                    vals['stitch_type_selection'] = 'other'

            # Case 2: stitch_type_selection → stitch_type
            elif 'stitch_type_selection' in vals and 'stitch_type' not in vals:
                selection_labels = {
                    'jersey': 'Jersey',
                    'interlock': 'Interlock',
                    'rib': 'Rib',
                    '2x1_rib': '2x1 Rib',
                    '2x2_rib': '2x2 Rib',
                    'other': 'Other',
                }
                vals['stitch_type'] = selection_labels.get(vals['stitch_type_selection'], 'Other')

        # Create all in batch for efficiency
        return super(StitchLibrary, self).create(vals_list)

    
    def write(self, vals):
        """Ensure stitch_type and stitch_type_selection are in sync"""
        if 'stitch_type' in vals and not 'stitch_type_selection' in vals:
            # Try to set stitch_type_selection based on stitch_type
            stitch_type_lower = vals['stitch_type'].lower()
            if 'jersey' in stitch_type_lower:
                vals['stitch_type_selection'] = 'jersey'
            elif 'interlock' in stitch_type_lower:
                vals['stitch_type_selection'] = 'interlock'
            elif '2x1' in stitch_type_lower and 'rib' in stitch_type_lower:
                vals['stitch_type_selection'] = '2x1_rib'
            elif '2x2' in stitch_type_lower and 'rib' in stitch_type_lower:
                vals['stitch_type_selection'] = '2x2_rib'
            elif 'rib' in stitch_type_lower:
                vals['stitch_type_selection'] = 'rib'
            else:
                vals['stitch_type_selection'] = 'other'
        elif 'stitch_type_selection' in vals and not 'stitch_type' in vals:
            # Set stitch_type based on stitch_type_selection
            selection_labels = dict([
                ('jersey', 'Jersey'),
                ('interlock', 'Interlock'),
                ('rib', 'Rib'),
                ('2x1_rib', '2x1 Rib'),
                ('2x2_rib', '2x2 Rib'),
                ('other', 'Other')
            ])
            vals['stitch_type'] = selection_labels.get(vals['stitch_type_selection'], 'Other')
        
        return super(StitchLibrary, self).write(vals)
    
    _sql_constraints = [
        ('name_stitch_body_uniq', 'unique (name, stitch_type, body_part)', "This stitch combination already exists!")
    ]
