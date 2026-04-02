from odoo import models, fields, api, _
import logging
import base64


class StitchDensityWizard(models.TransientModel):
    _name = 'stitch.density.wizard'
    _description = 'Stitch Density Measurement Wizard'

    calibration_mo_id = fields.Many2one('mrp.production', string='Calibration Swatch MO', required=True)
    parent_garment_mo_id = fields.Many2one('mrp.production', string='Parent Garment MO')
    
    mode = fields.Selection([
        ('stitch_density', 'Stitch Density'),
        ('swatch_measurement', 'Swatch Measurement')
    ], string='Mode', default='swatch_measurement')
    
    measurement_unit = fields.Selection([
        ('inches', 'Inches'),
        ('cm', 'CM')
    ], string='Measurement Unit', default='inches')
    
    body_swatch_specs_x = fields.Float(string='Body Swatch Specs X (courses)', default=200.0)
    body_swatch_specs_y = fields.Float(string='Body Swatch Specs Y (wales)', default=200.0)
    cuff_swatch_specs_x = fields.Float(string='Cuff Swatch Specs X (courses)', default=50.0)
    cuff_swatch_specs_y = fields.Float(string='Cuff Swatch Specs Y (wales)', default=200.0)
    
    # Body measurements
    body_measurement_x = fields.Float(string='Body Measurement X', default=8.0)
    body_measurement_y = fields.Float(string='Body Measurement Y', default=6.0)
    
    # Cuff measurements
    cuff_measurement_x = fields.Float(string='Cuff Measurement X', default=8.0)
    cuff_measurement_y = fields.Float(string='Cuff Measurement Y', default=2.0)
    
    body_calibration_x = fields.Float(string='Body Calibration X', compute='_compute_calibration_values', store=False)
    body_calibration_y = fields.Float(string='Body Calibration Y', compute='_compute_calibration_values', store=False)
    cuff_calibration_x = fields.Float(string='Cuff Calibration X', compute='_compute_calibration_values', store=False)
    cuff_calibration_y = fields.Float(string='Cuff Calibration Y', compute='_compute_calibration_values', store=False)
    
    width_image = fields.Binary(string='Width Image', attachment=True)
    width_image_filename = fields.Char(string='Width Image Filename')
    height_image = fields.Binary(string='Height Image', attachment=True)
    height_image_filename = fields.Char(string='Height Image Filename')
    width_image_2 = fields.Binary(string='Width Image 2', attachment=True)
    width_image_2_filename = fields.Char(string='Width Image 2 Filename')
    height_image_2 = fields.Binary(string='Height Image 2', attachment=True)
    height_image_2_filename = fields.Char(string='Height Image 2 Filename')

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        mo_id = defaults.get('calibration_mo_id')
        if not mo_id:
            return defaults

        mo = self.env['mrp.production'].browse(mo_id)
        cal_data = mo.calibration_data or {}
        if isinstance(cal_data, str):
            import json
            try:
                cal_data = json.loads(cal_data)
            except Exception:
                cal_data = {}

        if not isinstance(cal_data, dict) or not cal_data:
            return defaults

        # Measurement unit
        if cal_data.get('measurementUnit'):
            defaults['measurement_unit'] = cal_data['measurementUnit']

        # Swatch specs
        for py_key, js_key in [
            ('body_swatch_specs_x', 'bodySwatchSpecsX'),
            ('body_swatch_specs_y', 'bodySwatchSpecsY'),
            ('cuff_swatch_specs_x', 'cuffSwatchSpecsX'),
            ('cuff_swatch_specs_y', 'cuffSwatchSpecsY'),
            ('body_measurement_x',  'bodyMeasurementX'),
            ('body_measurement_y',  'bodyMeasurementY'),
            ('cuff_measurement_x',  'cuffMeasurementX'),
            ('cuff_measurement_y',  'cuffMeasurementY'),
        ]:
            val = cal_data.get(js_key)
            if val is not None:
                try:
                    defaults[py_key] = float(val)
                except (TypeError, ValueError):
                    pass

        # Images from attachment IDs
        Attachment = self.env['ir.attachment']
        for py_field, js_key in [
            ('width_image',   'widthImageAttachmentId'),
            ('height_image',  'heightImageAttachmentId'),
            ('width_image_2', 'widthImage2AttachmentId'),
            ('height_image_2','heightImage2AttachmentId'),
        ]:
            att_id = cal_data.get(js_key)
            if isinstance(att_id, list):
                att_id = att_id[0] if att_id else None
            if att_id:
                try:
                    att = Attachment.browse(int(att_id))
                    if att.exists() and att.datas:
                        defaults[py_field] = att.datas
                except (TypeError, ValueError):
                    pass

        return defaults

    @api.depends('body_swatch_specs_x', 'body_swatch_specs_y', 'body_measurement_x', 'body_measurement_y',
                 'cuff_swatch_specs_x', 'cuff_swatch_specs_y', 'cuff_measurement_x', 'cuff_measurement_y')
    def _compute_calibration_values(self):
        for wizard in self:
            wizard.body_calibration_x = wizard.body_swatch_specs_x / wizard.body_measurement_x if wizard.body_measurement_x > 0 else 0
            wizard.body_calibration_y = wizard.body_swatch_specs_y / wizard.body_measurement_y if wizard.body_measurement_y > 0 else 0
            wizard.cuff_calibration_x = wizard.cuff_swatch_specs_x / wizard.cuff_measurement_x if wizard.cuff_measurement_x > 0 else 0
            wizard.cuff_calibration_y = wizard.cuff_swatch_specs_y / wizard.cuff_measurement_y if wizard.cuff_measurement_y > 0 else 0

    def action_submit_measurements(self):
        """Submit stitch density measurements and navigate to parent garment MO"""
        self.ensure_one()
        
        logging.info(f" Custom Code: Submitting stitch density measurements for calibration MO: {self.calibration_mo_id.name}")
        
        # Get current calibration data from calibration MO
        calibration_data = self.calibration_mo_id.calibration_data.copy() if isinstance(self.calibration_mo_id.calibration_data, dict) else {}
        
        calibration_data.update({
            'bodySwatchSpecsX': self.body_swatch_specs_x,
            'bodySwatchSpecsY': self.body_swatch_specs_y,
            'cuffSwatchSpecsX': self.cuff_swatch_specs_x,
            'cuffSwatchSpecsY': self.cuff_swatch_specs_y,
            'bodyMeasurementX': self.body_measurement_x,
            'bodyMeasurementY': self.body_measurement_y,
            'bodyMeasurementXUnit': self.measurement_unit,
            'bodyMeasurementYUnit': self.measurement_unit,
            'cuffMeasurementX': self.cuff_measurement_x,
            'cuffMeasurementY': self.cuff_measurement_y,
            'cuffMeasurementXUnit': self.measurement_unit,
            'cuffMeasurementYUnit': self.measurement_unit,
        })
        
        Attachment = self.env['ir.attachment']
        
        if self.width_image:
            attachment = Attachment.create({
                'name': f'width_image_{self.calibration_mo_id.name}.png',
                'type': 'binary',
                'datas': self.width_image,
                'res_model': 'mrp.production',
                'res_id': self.calibration_mo_id.id,
                'res_field': 'width_image',
                'mimetype': 'image/png',
            })
            calibration_data['widthImageAttachmentId'] = attachment.id
            
        if self.height_image:
            attachment = Attachment.create({
                'name': f'height_image_{self.calibration_mo_id.name}.png',
                'type': 'binary',
                'datas': self.height_image,
                'res_model': 'mrp.production',
                'res_id': self.calibration_mo_id.id,
                'res_field': 'height_image',
                'mimetype': 'image/png',
            })
            calibration_data['heightImageAttachmentId'] = attachment.id

        if self.width_image_2:
            attachment = Attachment.create({
                'name': f'width_image_2_{self.calibration_mo_id.name}.png',
                'type': 'binary',
                'datas': self.width_image_2,
                'res_model': 'mrp.production',
                'res_id': self.calibration_mo_id.id,
                'res_field': 'width_image_2',
                'mimetype': 'image/png',
            })
            calibration_data['widthImage2AttachmentId'] = attachment.id
            
        if self.height_image_2:
            attachment = Attachment.create({
                'name': f'height_image_2_{self.calibration_mo_id.name}.png',
                'type': 'binary',
                'datas': self.height_image_2,
                'res_model': 'mrp.production',
                'res_id': self.calibration_mo_id.id,
                'res_field': 'height_image_2',
                'mimetype': 'image/png',
            })
            calibration_data['heightImage2AttachmentId'] = attachment.id
        
        # Calculate calibration values
        if self.body_measurement_x > 0:
            calibration_data['bodyCalibrationX'] = f"{(self.body_swatch_specs_x / self.body_measurement_x):.2f}"
        if self.body_measurement_y > 0:
            calibration_data['bodyCalibrationY'] = f"{(self.body_swatch_specs_y / self.body_measurement_y):.2f}"
        if self.cuff_measurement_x > 0:
            calibration_data['cuffCalibrationX'] = f"{(self.cuff_swatch_specs_x / self.cuff_measurement_x):.2f}"
        if self.cuff_measurement_y > 0:
            calibration_data['cuffCalibrationY'] = f"{(self.cuff_swatch_specs_y / self.cuff_measurement_y):.2f}"
        
       
        # Update calibration MO with measurements
        self.calibration_mo_id.write({'calibration_data': calibration_data})

        if self.calibration_mo_id.bom_request_id:
            self.calibration_mo_id.bom_request_id.write({'calibration_data': calibration_data})
            logging.info(f" Custom Code: Synced calibration data to BOM request: {self.calibration_mo_id.bom_request_id.name}")

        if self.parent_garment_mo_id:
            # Calibration swatch: copy data + images to parent garment MO and unblock it
            parent_calibration_data = calibration_data.copy()
            parent_calibration_data['hasPreExistingSwatch'] = True
            parent_calibration_data['calibrationSwatchId'] = self.calibration_mo_id.product_id.id

            # Duplicate attachments for parent MO
            if calibration_data.get('widthImageAttachmentId'):
                orig_attachment = Attachment.browse(calibration_data['widthImageAttachmentId'])
                if orig_attachment.exists():
                    new_attachment = Attachment.create({
                        'name': f'width_image_{self.parent_garment_mo_id.name}.png',
                        'type': 'binary',
                        'datas': orig_attachment.datas,
                        'res_model': 'mrp.production',
                        'res_id': self.parent_garment_mo_id.id,
                        'res_field': 'width_image',
                        'mimetype': 'image/png',
                    })
                    parent_calibration_data['widthImageAttachmentId'] = new_attachment.id

            if calibration_data.get('heightImageAttachmentId'):
                orig_attachment = Attachment.browse(calibration_data['heightImageAttachmentId'])
                if orig_attachment.exists():
                    new_attachment = Attachment.create({
                        'name': f'height_image_{self.parent_garment_mo_id.name}.png',
                        'type': 'binary',
                        'datas': orig_attachment.datas,
                        'res_model': 'mrp.production',
                        'res_id': self.parent_garment_mo_id.id,
                        'res_field': 'height_image',
                        'mimetype': 'image/png',
                    })
                    parent_calibration_data['heightImageAttachmentId'] = new_attachment.id

            if calibration_data.get('widthImage2AttachmentId'):
                orig_attachment = Attachment.browse(calibration_data['widthImage2AttachmentId'])
                if orig_attachment.exists():
                    new_attachment = Attachment.create({
                        'name': f'width_image_2_{self.parent_garment_mo_id.name}.png',
                        'type': 'binary',
                        'datas': orig_attachment.datas,
                        'res_model': 'mrp.production',
                        'res_id': self.parent_garment_mo_id.id,
                        'res_field': 'width_image_2',
                        'mimetype': 'image/png',
                    })
                    parent_calibration_data['widthImage2AttachmentId'] = new_attachment.id

            if calibration_data.get('heightImage2AttachmentId'):
                orig_attachment = Attachment.browse(calibration_data['heightImage2AttachmentId'])
                if orig_attachment.exists():
                    new_attachment = Attachment.create({
                        'name': f'height_image_2_{self.parent_garment_mo_id.name}.png',
                        'type': 'binary',
                        'datas': orig_attachment.datas,
                        'res_model': 'mrp.production',
                        'res_id': self.parent_garment_mo_id.id,
                        'res_field': 'height_image_2',
                        'mimetype': 'image/png',
                    })
                    parent_calibration_data['heightImage2AttachmentId'] = new_attachment.id

            self.parent_garment_mo_id.write({'calibration_data': parent_calibration_data})
            self.parent_garment_mo_id.write({'is_blocked_for_calibration': False})
            logging.info(f" Custom Code: Unblocked parent garment MO: {self.parent_garment_mo_id.name}")

            # Mark calibration MO as done (skip immediate-transfer wizard)
            cal_mo = self.calibration_mo_id
            if not cal_mo.qty_producing:
                cal_mo.qty_producing = cal_mo.product_qty
            cal_mo.with_context(skip_stitch_density_wizard=True, skip_immediate=True).button_mark_done()

            # Navigate to the parent garment MO
            return {
                'type': 'ir.actions.act_window',
                'name': _('Garment Manufacturing Order'),
                'res_model': 'mrp.production',
                'res_id': self.parent_garment_mo_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            # Standalone swatch: no parent MO — stitch density saved, stay on this MO
            logging.info(f" Custom Code: Standalone swatch — stitch density saved to {self.calibration_mo_id.name}, no parent to unblock")
            return {
                'type': 'ir.actions.act_window',
                'name': _('Manufacturing Order'),
                'res_model': 'mrp.production',
                'res_id': self.calibration_mo_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
