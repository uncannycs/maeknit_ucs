from odoo import models, fields, api
import logging
import re

UPS_RE = r'\b1Z[0-9A-Z]{16}\b'
FEDEX_RE = r'\b(\d{12}|\d{15}|\d{20})\b'
USPS_RE = r'\b(9400\d{17}|9205\d{17}|9303\d{17}|9470\d{17}|\d{20,22})\b'
DHL_RE = r'\b(\d{10})\b'

class ShippingMail(models.Model):
    _name = "maeknit.shipping.mail"
    _inherit = ["mail.thread"]
    _description = "Shipping Mail Debugger"

    subject = fields.Char(string="Subject")
    body = fields.Html(string="Email Body")
    email_from = fields.Char(string="Email From")
    tracking_ids = fields.One2many('maeknit.shipping.tracking', 'email_id', string="Tracking Numbers")
    tracking_count = fields.Integer(compute="_compute_tracking_count", string="Tracking Count")

    @api.depends('tracking_ids')
    def _compute_tracking_count(self):
        for record in self:
            record.tracking_count = len(record.tracking_ids)

    def message_new(self, msg_dict, custom_values=None):
        """Called when a new email is received"""
        if custom_values is None:
            custom_values = {}
        
        subject = msg_dict.get('subject', 'No Subject')
        email_from = msg_dict.get('from', msg_dict.get('email_from', 'Unknown'))
        body = msg_dict.get('body', '')
        
        logging.info(" Custom Code:="*60)
        logging.info(" Custom Code: NEW EMAIL RECEIVED")
        logging.info(" Custom Code:="*60)
        logging.info(" Custom Code:Subject: %s", subject)
        logging.info(" Custom Code:From: %s", email_from)
        logging.info(" Custom Code:Body length: %s", len(body))
        
        custom_values.update({
            'subject': subject,
            'email_from': email_from,
            'body': body,
        })
        
        res = super().message_new(msg_dict, custom_values)

        # Extract text from HTML body for pattern matching
        body_text = (body or "").replace("<br>", " ").replace("<div>", " ").replace("</div>", " ")

        logging.info(" Custom Code:=================================================")
        logging.info(" Custom Code: EXTRACTING TRACKING NUMBERS ")
        logging.info(" Custom Code:=================================================")
        try:
            ups_numbers = re.findall(UPS_RE, body_text)
            fedex_numbers = re.findall(FEDEX_RE, body_text)
            usps_numbers = re.findall(USPS_RE, body_text)
            dhl_numbers = re.findall(DHL_RE, body_text)

            logging.info(" Custom Code:UPS: %s", ups_numbers)
            logging.info(" Custom Code:FedEx: %s", fedex_numbers)
            logging.info(" Custom Code:USPS: %s", usps_numbers)
            logging.info(" Custom Code:DHL: %s", dhl_numbers)
            
            carrier_map = {}

            for num in ups_numbers:
                carrier_map[num] = "ups"

            for num in fedex_numbers:
                carrier_map[num] = "fedex"

            for num in usps_numbers:
                carrier_map[num] = "usps"

            for num in dhl_numbers:
                carrier_map[num] = "dhl_express"
                
            tracking_model = self.env['maeknit.shipping.tracking']
            for tn, carrier in carrier_map.items():
                tracking_model.create({
                    'tracking_number': tn,
                    'carrier_code': carrier,
                    'email_id': res.id,
                })
                
            logging.info(" Custom Code:Detected Carriers: %s", carrier_map)
            logging.info(" Custom Code:Created %s tracking records", len(carrier_map))
        except Exception as e:
            logging.error("Error extracting tracking numbers: %s", e)
        
        return res

    def action_extract_tracking(self):
        """Manual button to extract tracking numbers from email body"""
        for record in self:
            body_text = (record.body or "").replace("<br>", " ").replace("<div>", " ").replace("</div>", " ")
            
            logging.info(" Custom Code:=== Manual Extraction for Email ID %s ===", record.id)
            
            ups_numbers = re.findall(UPS_RE, body_text)
            fedex_numbers = re.findall(FEDEX_RE, body_text)
            usps_numbers = re.findall(USPS_RE, body_text)
            dhl_numbers = re.findall(DHL_RE, body_text)

            carrier_map = {}
            for num in ups_numbers:
                carrier_map[num] = "ups"
            for num in fedex_numbers:
                carrier_map[num] = "fedex"
            for num in usps_numbers:
                carrier_map[num] = "usps"
            for num in dhl_numbers:
                carrier_map[num] = "dhl_express"
            
            tracking_model = self.env['maeknit.shipping.tracking']
            created_count = 0
            for tn, carrier in carrier_map.items():
                # Check if tracking number already exists for this email
                existing = tracking_model.search([
                    ('tracking_number', '=', tn),
                    ('email_id', '=', record.id)
                ], limit=1)
                
                if not existing:
                    tracking_model.create({
                        'tracking_number': tn,
                        'carrier_code': carrier,
                        'email_id': record.id,
                    })
                    created_count += 1
                    
            logging.info(" Custom Code:Created %s new tracking records", created_count)
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Tracking Numbers Extracted',
                'message': f'{created_count} new tracking number(s) found and created.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_fetch_emails(self):
        """Fetch emails from all configured mail servers"""
        logging.info(" Custom Code:="*60)
        logging.info(" Custom Code: Manual Email Fetch Triggered")
        logging.info(" Custom Code:="*60)
        
        try:
            # Trigger mail server fetch using standard mail methods
            MailServer = self.env['fetchmail.server'].sudo()
            servers = MailServer.search([('state', '=', 'done')])
            
            if not servers:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'No Mail Server',
                        'message': 'Please configure an incoming mail server in Settings > Technical > Incoming Mail Servers.',
                        'type': 'warning',
                        'sticky': False,
                    }
                }
            
            fetched_count = 0
            for server in servers:
                try:
                    server.fetch_mail()
                    fetched_count += 1
                    logging.info(" Custom Code:✓ Fetched emails from server: %s", server.name)
                except Exception as e:
                    logging.error("✗ Error fetching from server %s: %s", server.name, str(e))
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Emails Fetched',
                    'message': f'Successfully fetched emails from {fetched_count} server(s).',
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            logging.error("Error in manual email fetch: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Fetch Failed',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_view_tracking(self):
        """Open tracking numbers related to this email"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tracking Numbers',
            'res_model': 'maeknit.shipping.tracking',
            'view_mode': 'list,form',
            'domain': [('email_id', '=', self.id)],
            'context': {'default_email_id': self.id}
        }
