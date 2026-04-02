from odoo import models, fields, api, _
import logging
import copy  # Added for deep copying JSON data


class WholeCadMeasurementWizard(models.TransientModel):
    _name = 'whole.cad.measurement.wizard'
    _description = 'Whole CAD Actual Measurement Wizard'

    workorder_id = fields.Many2one('mrp.workorder', string='Work Order', required=True)
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', required=True)
    measurement_line_ids = fields.One2many(
        'whole.cad.measurement.wizard.line',
        'wizard_id',
        string='Measurements'
    )
    unit = fields.Selection([
        ('inches', 'Inches'),
        ('cm', 'CM')
    ], string='Unit', default='inches', readonly=True)

    @api.model
    def default_get(self, fields_list):
        """Populate wizard with measurements from whole_cad_data"""
        res = super().default_get(fields_list)
        
        if self.env.context.get('default_production_id'):
            production = self.env['mrp.production'].browse(self.env.context['default_production_id'])
            
            # Get whole_cad_data
            whole_cad_data = production.whole_cad_data if isinstance(production.whole_cad_data, dict) else {}
            measurements = whole_cad_data.get('measurements', [])
            unit = whole_cad_data.get('unit', 'inches')
            max_version = whole_cad_data.get('max_version', 0)
            
            res['unit'] = unit
            
            # Create line values from measurements - only include rows that have data
            line_vals = []
            for idx, measurement in enumerate(measurements):
                if isinstance(measurement, dict):
                    # Check if this measurement has any meaningful data
                    point = measurement.get('point', '')
                    name = measurement.get('name', '')
                    request = measurement.get('request', '')
                    
                    # Only add rows that have at least a name or request value
                    if name or request:
                        line_vals.append((0, 0, {
                            'sequence': idx + 1,
                            'point': point,
                            'name': name,
                            'tolerance': float(measurement.get('tolerance', 0) or 0),
                            'expected_value': float(request or 0),
                            'actual_value': 0.0,  # Start fresh at 0
                        }))
            
            res['measurement_line_ids'] = line_vals
            
            logging.info(f" Custom Code: Loaded {len(line_vals)} measurements into wizard for MO {production.name}")
        
        return res

    def action_submit_measurements(self):
        """Submit actual measurements and trigger CAD version bump"""
        self.ensure_one()
        logging.info(f" Custom Code: [WIZARD] Submitting actual measurements for WO: {self.workorder_id.name}, MO: {self.production_id.name}")
        
        whole_cad_data = self.production_id.whole_cad_data or {}
        measurements = whole_cad_data.get('measurements', [])
        max_version = whole_cad_data.get('max_version', 0)
        next_version = max_version + 1
        
        logging.info(f" Custom Code: [WIZARD] Current max_version: {max_version}, bumping to: {next_version}")
        logging.info(f" Custom Code: [WIZARD] Total wizard lines: {len(self.measurement_line_ids)}")
        logging.info(f" Custom Code: [WIZARD] Total measurements in JSON: {len(measurements)}")
        
        # Match by sequence/index since name and point are False in wizard lines
        matched_count = 0
        for idx, line in enumerate(self.measurement_line_ids):
            # Match by index position instead of name/point
            if idx < len(measurements):
                measurement = measurements[idx]
                measurement[f'v{next_version}'] = str(line.actual_value) if line.actual_value else ""
                matched_count += 1
                logging.info(f" Custom Code: [WIZARD] Matched line {idx}: {measurement.get('name', 'N/A')} = {line.actual_value}")
            else:
                logging.warning(f"[WIZARD] Line {idx} has no matching measurement in JSON")
        
        logging.info(f" Custom Code: [WIZARD] Successfully matched {matched_count}/{len(self.measurement_line_ids)} lines")
        
        # Update max version
        whole_cad_data['max_version'] = next_version
        whole_cad_data['measurements'] = measurements
        
        logging.info(f" Custom Code: [WIZARD] Updated whole_cad_data with {len(measurements)} measurements and max_version={next_version}")
        
        # Write to production order (which will auto-sync to BOM Request via the MO's write method)
        self.production_id.write({
            'whole_cad_data': whole_cad_data,
            'wizard_measurements_submitted': True,
        })
        
        bom_requests = self.env['maeknit.bom.request'].search([
                ('mo_id', '=', self.production_id.id)
            ])

        for bom_request in bom_requests:
            bom_request.action_ready_to_spec()
        
        logging.info(f" Custom Code: [WIZARD] Successfully saved measurements to MO {self.production_id.name}")
        
        # Now finish the workorder
        return self.workorder_id.button_finish()


class WholeCadMeasurementWizardLine(models.TransientModel):
    _name = 'whole.cad.measurement.wizard.line'
    _description = 'Whole CAD Measurement Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('whole.cad.measurement.wizard', string='Wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    point = fields.Char(string='Point', readonly=True)
    name = fields.Char(string='Measurement Name', readonly=True)
    tolerance = fields.Float(string='Tolerance', digits=(16, 3), readonly=True)
    expected_value = fields.Float(string='Expected Value', digits=(16, 3), readonly=True)
    actual_value = fields.Float(string='Actual Value', digits=(16, 3), required=True)
    variance = fields.Float(string='Variance', compute='_compute_variance', store=True, digits=(16, 3))
    variance_percentage = fields.Float(string='Variance %', compute='_compute_variance', store=True, digits=(16, 2))
    is_out_of_tolerance = fields.Boolean(string='Out of Tolerance', compute='_compute_variance', store=True)

    @api.depends('expected_value', 'actual_value', 'tolerance')
    def _compute_variance(self):
        """Calculate variance between expected and actual values"""
        for line in self:
            line.variance = line.actual_value - line.expected_value
            if line.expected_value != 0:
                line.variance_percentage = (line.variance / line.expected_value) * 100
            else:
                line.variance_percentage = 0.0
            
            # Check if out of tolerance
            if line.tolerance > 0:
                line.is_out_of_tolerance = abs(line.variance) > line.tolerance
            else:
                line.is_out_of_tolerance = False
