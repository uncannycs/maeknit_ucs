from odoo import models, fields, api, _
import logging

class CalibrationSwatchConfirmWizard(models.TransientModel):
    _name = 'calibration.swatch.confirm.wizard'
    _description = 'Calibration Swatch Confirmation Wizard'

    mo_id = fields.Many2one('mrp.production', string='Manufacturing Order', required=True)
    generate_swatch = fields.Boolean(string='Generate Calibration Swatch', default=True)

    def action_confirm(self):
        """Confirm the MO and optionally generate calibration swatch"""
        self.ensure_one()
        
        if self.generate_swatch:
            # Generate calibration swatch and navigate to it
            logging.info(f"Generating calibration swatch for MO: {self.mo_id.name}")
            
            # Mark the original MO as blocked for calibration
            self.mo_id.write({'is_blocked_for_calibration': True})
            
            # Generate the calibration swatch MO
            action = self.mo_id.action_generate_calibration_swatch()
            
            # Link the calibration swatch MO to the parent garment MO
            if action and action.get('res_id'):
                calibration_mo = self.env['mrp.production'].browse(action['res_id'])
                calibration_mo.write({
                    'parent_garment_mo_id': self.mo_id.id,
                    'origin_mo_id': self.mo_id.id,
                })
                self.mo_id.write({'calibration_swatch_mo_id': calibration_mo.id})
            
            # Confirm the original MO
            self.mo_id.with_context(skip_calibration_wizard=True).action_confirm()
            
            return action
        else:
            # Just confirm the MO without generating calibration swatch
            logging.info(f"Confirming MO without calibration swatch: {self.mo_id.name}")
            return self.mo_id.with_context(skip_calibration_wizard=True).action_confirm()
