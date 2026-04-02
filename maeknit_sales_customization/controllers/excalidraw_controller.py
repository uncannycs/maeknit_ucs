from odoo import http
from odoo.http import request
import json
import logging
import base64

class ExcalidrawImageController(http.Controller):
    
    @http.route('/maeknit/measurement/panel/<int:record_id>/<string:panel_name>', 
                type='http', auth='user', methods=['GET'])
    def get_measurement_panel_image(self, record_id, panel_name, model=None, **kwargs):
        """Serve Measurement panel image from attachment
        
        Args:
            record_id: ID of the BOM Request record
            panel_name: Name of the panel (front, back, sleeve, collar, or custom panel ID)
            model: Optional model name parameter
        """
        try:
            # Get the BOM Request
            bom_request = request.env['maeknit.bom.request'].browse(record_id)
            if not bom_request.exists():
                logging.warning(f"BOM Request {record_id} not found")
                return request.not_found()
            
            # Get measurement data
            if not bom_request.measurement_widget_data:
                logging.warning(f"No measurement data for BOM Request {record_id}")
                return request.not_found()
            
            try:
                if isinstance(bom_request.measurement_widget_data, str):
                    measurement_data = json.loads(bom_request.measurement_widget_data)
                else:
                    measurement_data = bom_request.measurement_widget_data
            except (ValueError, TypeError, json.JSONDecodeError):
                logging.error(f"Failed to parse measurement data for BOM Request {record_id}")
                return request.not_found()
            
            # Get the image attachment ID from the panel.
            # Suffix conventions in URLs:
            #   _2         → image2_attachment_id  (structure image)
            #   _annotated → annotated_image_attachment_id (generated annotation)
            #   (none)     → image_attachment_id   (original)
            image_attachment_id = None
            image_field = 'image_attachment_id'
            actual_panel_name = panel_name
            if panel_name.endswith('_annotated'):
                image_field = 'annotated_image_attachment_id'
                actual_panel_name = panel_name[:-len('_annotated')]
            elif panel_name.endswith('_2'):
                image_field = 'image2_attachment_id'
                actual_panel_name = panel_name[:-2]

            panel_data = measurement_data.get(actual_panel_name, {})
            image_attachment_id = panel_data.get(image_field)
            
            if not image_attachment_id:
                logging.warning(f"No image attachment for panel '{panel_name}' in BOM Request {record_id}")
                return request.not_found()
            
            # Get the attachment
            attachment = request.env['ir.attachment'].browse(image_attachment_id)
            if not attachment.exists() or not attachment.datas:
                logging.warning(f"Attachment {image_attachment_id} not found or has no data")
                return request.not_found()
            
            # Get base64 data and decode to binary
            base64_data = attachment.datas
            if isinstance(base64_data, bytes):
                base64_data = base64_data.decode('utf-8')
            
            # Clean base64 data
            base64_data = ''.join(base64_data.split())
            
            # Get mime type
            mime_type = attachment.mimetype or 'image/png'
            
            # Decode base64 to binary for image response
            try:
                image_binary = base64.b64decode(base64_data)
            except Exception as decode_error:
                logging.error(f"Failed to decode base64 data: {decode_error}")
                return request.not_found()
            
            # Return image directly as binary
            return request.make_response(image_binary, [
                ('Content-Type', mime_type),
                ('Content-Disposition', f'inline; filename="{attachment.name}"'),
                ('Cache-Control', 'no-store, max-age=0, must-revalidate'),
            ])
            
        except Exception as e:
            logging.error(f"Error serving measurement panel image: {str(e)}", exc_info=True)
            return request.not_found()
    
    @http.route('/maeknit/whole_cad/image/<int:record_id>', 
                type='http', auth='user', methods=['GET'])
    def get_whole_cad_image(self, record_id, model=None, **kwargs):
        """Serve Whole CAD image from attachment
        
        Args:
            record_id: ID of the record (BOM Request, MRP Production, or MRP Workorder)
            model: Optional model name to specify which model to use
        """
        try:
            # Determine which model to use
            models_to_try = []
            
            if model:
                models_to_try.append(model)
            else:
                # Try in order: BOM Request, MRP Production, MRP Workorder
                models_to_try = ['maeknit.bom.request', 'mrp.production', 'mrp.workorder']
            
            record = None
            bom_request = None
            
            for model_name in models_to_try:
                try:
                    candidate = request.env[model_name].browse(record_id)
                    if candidate.exists():
                        record = candidate
                        
                        # Get the BOM Request (source of whole_cad_image_id)
                        if model_name == 'maeknit.bom.request':
                            bom_request = record
                        elif model_name == 'mrp.production':
                            bom_request = record.bom_request_id
                        elif model_name == 'mrp.workorder':
                            bom_request = record.production_id.bom_request_id if record.production_id else None
                        
                        if bom_request and bom_request.exists():
                            break
                except Exception as e:
                    logging.info(f"Model {model_name} not found or error: {e}")
                    continue
            
            if not record:
                logging.warning(f"Record ID {record_id} not found")
                return request.not_found()

            # Resolve attachment: prefer bom_request.whole_cad_image_id,
            # fall back to image_attachment_id stored in whole_cad_data (standalone MO).
            attachment = None
            if bom_request and bom_request.exists():
                attachment = bom_request.whole_cad_image_id
            if (not attachment or not attachment.exists()) and hasattr(record, 'whole_cad_data'):
                att_id = (record.whole_cad_data or {}).get('image_attachment_id')
                if att_id:
                    attachment = request.env['ir.attachment'].browse(att_id)

            if not attachment or not attachment.exists() or not attachment.datas:
                logging.warning(f"No whole CAD image found for record {record_id}")
                return request.not_found()
            
            # Get base64 data and clean it
            base64_data = attachment.datas
            if isinstance(base64_data, bytes):
                base64_data = base64_data.decode('utf-8')
            
            # Clean base64 data - remove all whitespace
            base64_data = ''.join(base64_data.split())
            
            # Get mime type
            mime_type = attachment.mimetype or 'image/png'
            
            # Return JSON with dataURL
            return request.make_json_response({
                'dataURL': f"data:{mime_type};base64,{base64_data}",
                'mimeType': mime_type,
                'created': int(attachment.create_date.timestamp() * 1000) if attachment.create_date else 0,
            })
            
        except Exception as e:
            logging.error(f"Error serving whole CAD image: {str(e)}", exc_info=True)
            return request.not_found()

    @http.route('/maeknit/cad_pom/image/<int:record_id>',
                type='http', auth='user', methods=['GET'])
    def get_cad_pom_image(self, record_id, model=None, **kwargs):
        """Serve CAD & POM image from attachment"""
        try:
            models_to_try = []

            if model:
                models_to_try.append(model)
            else:
                models_to_try = ['maeknit.bom.request', 'mrp.production', 'mrp.workorder']

            record = None
            bom_request = None

            for model_name in models_to_try:
                try:
                    candidate = request.env[model_name].browse(record_id)
                    if candidate.exists():
                        record = candidate

                        if model_name == 'maeknit.bom.request':
                            bom_request = record
                        elif model_name == 'mrp.production':
                            bom_request = record.bom_request_id
                        elif model_name == 'mrp.workorder':
                            bom_request = record.production_id.bom_request_id if record.production_id else None

                        if bom_request and bom_request.exists():
                            break
                except Exception as e:
                    logging.info(f"Model {model_name} not found or error: {e}")
                    continue

            if not record:
                return request.not_found()

            attachment = None
            if bom_request and bom_request.exists():
                attachment = bom_request.cad_pom_image_id
            if (not attachment or not attachment.exists()) and hasattr(record, 'cad_pom_data'):
                att_id = (record.cad_pom_data or {}).get('image_attachment_id')
                if att_id:
                    attachment = request.env['ir.attachment'].browse(att_id)

            if not attachment or not attachment.exists() or not attachment.datas:
                return request.not_found()

            base64_data = attachment.datas
            if isinstance(base64_data, bytes):
                base64_data = base64_data.decode('utf-8')

            base64_data = ''.join(base64_data.split())
            mime_type = attachment.mimetype or 'image/png'

            return request.make_json_response({
                'dataURL': f"data:{mime_type};base64,{base64_data}",
                'mimeType': mime_type,
                'created': int(attachment.create_date.timestamp() * 1000) if attachment.create_date else 0,
            })

        except Exception as e:
            logging.error(f"Error serving CAD & POM image: {str(e)}", exc_info=True)
            return request.not_found()

    @http.route('/maeknit/excalidraw/image/<int:record_id>/<string:file_id>', 
                type='http', auth='user', methods=['GET'])
    def get_excalidraw_image(self, record_id, file_id, model=None, **kwargs):
        """Serve Excalidraw image as base64 data URL
        
        Args:
            record_id: ID of the record (BOM Request, MRP Production, or MRP Workorder)
            file_id: Excalidraw file ID
            model: Optional model name to specify which model to use
        """
        try:
            # Determine which model to use
            # Priority: explicit model parameter, then try each model
            models_to_try = []
            
            if model:
                models_to_try.append(model)
            else:
                # Try in order: BOM Request, MRP Production, MRP Workorder
                models_to_try = ['maeknit.bom.request', 'mrp.production', 'mrp.workorder']
            
            record = None
            bom_request = None
            
            for model_name in models_to_try:
                try:
                    candidate = request.env[model_name].browse(record_id)
                    if candidate.exists():
                        record = candidate
                        logging.info(f" Custom Code: Found record in model {model_name} with ID {record_id}")
                        
                        # Get the BOM Request (source of excalidraw_data)
                        if model_name == 'maeknit.bom.request':
                            bom_request = record
                        elif model_name == 'mrp.production':
                            bom_request = record.bom_request_id
                        elif model_name == 'mrp.workorder':
                            bom_request = record.production_id.bom_request_id if record.production_id else None
                        
                        if bom_request and bom_request.exists():
                            break
                except Exception as e:
                    logging.error(f"Model {model_name} not found or error: {e}")
                    continue
            
            if not record:
                logging.info(f" Custom Code: Record ID {record_id} not found in any model")
                return request.not_found()

            # Check BOM Request fields first, then fall back to the record itself
            attachment_id = None

            records_to_check = []
            if bom_request and bom_request.exists():
                records_to_check.append((bom_request, ('excalidraw_data', 'garment_construction_data', 'structure_cad_data')))
            # Fallback: check record's own structure_cad_data (e.g. standalone MO or BOM request sync lag)
            if record is not bom_request:
                records_to_check.append((record, ('structure_cad_data', 'excalidraw_data', 'garment_construction_data')))

            for check_record, field_names in records_to_check:
                for field_name in field_names:
                    field_data = getattr(check_record, field_name, None)
                    if not field_data:
                        continue
                    if isinstance(field_data, str):
                        try:
                            field_data = json.loads(field_data)
                        except json.JSONDecodeError:
                            continue
                    elif not isinstance(field_data, dict):
                        continue
                    file_ids_map = field_data.get('fileIds', {})
                    attachment_id = file_ids_map.get(file_id)
                    if attachment_id:
                        break
                if attachment_id:
                    break

            if not attachment_id:
                logging.info(f" Custom Code: File ID {file_id} not found for record {record_id}")
                return request.not_found()
            
            # Get the attachment
            attachment = request.env['ir.attachment'].sudo().browse(attachment_id)
            
            if not attachment.exists() or not attachment.datas:
                logging.info(f" Custom Code: Attachment {attachment_id} not found or empty")
                return request.not_found()
            
            # Get base64 data
            base64_data = attachment.datas
            if isinstance(base64_data, bytes):
                base64_data = base64_data.decode('utf-8')
            
            # Get mime type
            mime_type = attachment.mimetype or 'image/png'
            
            logging.info(f" Custom Code: Successfully serving image {file_id} for record {record_id}")
            
            # Return JSON with dataURL
            return request.make_json_response({
                'dataURL': f"data:{mime_type};base64,{base64_data}",
                'mimeType': mime_type,
                'created': int(attachment.create_date.timestamp() * 1000) if attachment.create_date else 0,
            })
            
        except Exception as e:
            logging.error(f"Error serving Excalidraw image: {str(e)}", exc_info=True)
            return request.not_found()
