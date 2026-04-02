from odoo import models, fields, api
import logging
import base64
import requests


class ShippingTracking(models.Model):
    _name = "maeknit.shipping.tracking"
    _description = "Shipping Tracking Records"

    tracking_number = fields.Char(required=True)
    carrier_code = fields.Char()
    email_id = fields.Many2one("maeknit.shipping.mail", string="Source Email")

    status = fields.Char()
    last_event = fields.Char()
    raw_response = fields.Text()
    last_updated = fields.Datetime(string="Last Updated")

    def __str__(self):
        return f"{self.tracking_number} ({self.carrier_code})"

    def action_fetch_tracking(self):
        """Button action to fetch tracking status"""
        for record in self:
            try:
                data = record.fetch_shipstation_status()
                logging.info(" Custom Code:✓ Successfully fetched tracking for %s", record.tracking_number)
            except Exception as e:
                logging.error("✗ Error fetching tracking for %s: %s", record.tracking_number, str(e))
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': f'Failed to fetch tracking: {str(e)}',
                        'type': 'danger',
                        'sticky': False,
                    }
                }
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Tracking information updated successfully!',
                'type': 'success',
                'sticky': False,
            }
        }

    def fetch_shipstation_status(self):
        """Fetch tracking status from ShipStation API"""
        api_key = self.env["ir.config_parameter"].sudo().get_param("shipstation.api_key")
        api_secret = self.env["ir.config_parameter"].sudo().get_param("shipstation.api_secret")

        if not api_key or not api_secret:
            raise ValueError("ShipStation API credentials not configured. Please set shipstation.api_key and shipstation.api_secret in System Parameters.")

        auth = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}

        params = {
            "trackingNumber": self.tracking_number
        }
        if self.carrier_code:
            params["carrierCode"] = self.carrier_code

        url = "https://ssapi.shipstation.com/track"
        
        logging.info(" Custom Code:="*60)
        logging.info(" Custom Code:📦 Calling ShipStation API")
        logging.info(" Custom Code:="*60)
        logging.info(" Custom Code:URL: %s", url)
        logging.info(" Custom Code:Params: %s", params)
        logging.info(" Custom Code:Carrier: %s", self.carrier_code or "Not specified")

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            logging.info(" Custom Code:="*60)
            logging.info(" Custom Code:📬 ShipStation Response for %s", self.tracking_number)
            logging.info(" Custom Code:="*60)
            logging.info(" Custom Code:Status Code: %s", response.status_code)
            logging.info(" Custom Code:Response Data: %s", data)
            logging.info(" Custom Code:="*60)

            self.raw_response = response.text
            self.last_updated = fields.Datetime.now()
            
            # Extract status description
            if 'statusDescription' in data:
                self.status = data.get('statusDescription', 'Unknown')
            elif 'status' in data:
                self.status = data.get('status', 'Unknown')
            else:
                self.status = 'No status available'
            
            # Extract the latest event
            events = data.get("events", [])
            if events and len(events) > 0:
                # Events are typically in chronological order, get the last one
                latest_event = events[-1]
                event_desc = latest_event.get('description', latest_event.get('eventDescription', ''))
                event_location = latest_event.get('location', '')
                
                if event_location:
                    self.last_event = f"{event_desc} - {event_location}"
                else:
                    self.last_event = event_desc
                    
                logging.info(" Custom Code:Latest Event: %s", self.last_event)
            else:
                self.last_event = "No tracking events available"

            return data
            
        except requests.exceptions.RequestException as e:
            logging.error("="*60)
            logging.error("❌ API Request Failed")
            logging.error("="*60)
            logging.error("Error: %s", str(e))
            logging.error("="*60)
            raise
