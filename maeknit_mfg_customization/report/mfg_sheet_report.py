from odoo import models, api
import json
import logging

class ReportMfgSheet(models.AbstractModel):
    _name = 'report.maeknit_mfg_customization.report_mfg_sheet'
    _description = 'MFG Sheet Report'

    def _get_report_values(self, docids, data=None):
        productions = self.env['mrp.production'].browse(docids)
        report_docs = []
        for prod in productions:
            report_docs.append({
                'o': prod,
                'panels': self._prepare_panels(prod),
                'whole_cad': self._prepare_whole_cad(prod),
                'cal': self._parse_json_field(prod.calibration_data),
            })
        return {
            'doc_ids': docids,
            'doc_model': 'mrp.production',
            'docs': report_docs,
        }

    def _parse_json_field(self, value):
        """Return value as a dict, parsing from JSON string if necessary."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return {}

    def _get_attachment_b64(self, attachment_id):
        """Return base64-encoded string for an ir.attachment by ID, or None."""
        if not attachment_id:
            return None
        try:
            att = self.env['ir.attachment'].sudo().browse(int(attachment_id))
            if att.exists() and att.datas:
                datas = att.datas
                if isinstance(datas, bytes):
                    return datas.decode('ascii')
                return datas
        except Exception as e:
            logging.warning('MFG Sheet: could not load attachment %s: %s', attachment_id, e)
        return None

    def _prepare_panels(self, production):
        """Build a list of panel dicts with base64 images for the QWeb template."""
        data = production.measurement_widget_data
        if not data or not isinstance(data, dict):
            return []

        struct_panels = data.get('structurePanels', [])
        custom_panels = data.get('customPanels', [])
        hidden_panels = set(data.get('hiddenPanels', []))

        panels = []
        for panel_ref in struct_panels + custom_panels:
            panel_id = panel_ref.get('id', '')
            if panel_id in hidden_panels:
                continue
            panel_data = data.get(panel_id, {})
            panels.append({
                'name': panel_data.get('name') or panel_ref.get('name', ''),
                'measurements': panel_data.get('measurements', []),
                'image': self._get_attachment_b64(panel_data.get('image_attachment_id')),
                'image2': self._get_attachment_b64(panel_data.get('image2_attachment_id')),
            })
        return panels

    def _prepare_whole_cad(self, production):
        """Return whole-CAD dict with base64 image for the QWeb template."""
        data = production.whole_cad_data
        if not data or not isinstance(data, dict):
            return {'image': None, 'measurements': [], 'unit': 'inches'}
        return {
            'image': self._get_attachment_b64(data.get('image_attachment_id')),
            'measurements': data.get('measurements', []),
            'unit': data.get('unit', 'inches'),
        }
