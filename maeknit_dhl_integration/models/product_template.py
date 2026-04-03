import logging
import requests
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    hs_code = fields.Char(string="HS Code", help="Standardized code for international trade.")
    country_of_origin = fields.Many2one('res.country', string="Country of Origin")
    is_dhl = fields.Boolean(string="Is DHL", help="Mark this product as a DHL service product for shipping/duty charges.")
    is_generated = fields.Boolean(string="Is Generated", default=False)
    lookup_id = fields.Char(string="Dutify ID", copy=False)
    product_classification_name = fields.Char(string="Hs Code Description", readonly=True, copy=False)
    yarn_product_name = fields.Char(string="Auto yarn product name", copy=False)

    def _get_hs_code_search_name(self, purpose='sample'):
        """ Construct a searchable description for products based on category. """
        self.ensure_one()
        
        # Priority 1: Yarn category uses Fiber Composition logic
        if self.product_category == 'yarn':
            fiber_parts = [f"{f.percentage}% {f.fiber_type_id.name}" for f in self.fiber_ids]
            fibers_str = " ".join(fiber_parts)
            
            category_label = dict(self.fields_get(['product_category'])['product_category']['selection']).get(self.product_category, 'Yarn')
            name_parts = [p for p in [fibers_str, category_label, purpose] if p]
            return " ".join(name_parts)
            
        # Priority 2: Other categories (Garment, Accessories, etc.) use the Product Name
        else:
            name_parts = [p for p in [self.name, purpose] if p]
            return " ".join(name_parts)

    def action_generate_dhl_hs_code_backend(self, country_code, purpose='sample'):
        """
        Automated backend call to Dutify API to fetch HS code.
        Used during RFQ generation.
        """
        self.ensure_one()
        company = self.env.company
        if not company.dutify_api_key:
            _logger.warning("Missing Dutify API Key for company %s", company.name)
            return False

        description = self._get_hs_code_search_name(purpose=purpose)
        url = "https://dutify.com/api/v1/hs_lookups"
        payload = {"data": {
            "description": description,
            "country_code": country_code,
        }}
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "X-API-KEY": company.dutify_api_key
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            data = response.json()
            
            # Extract logic from the wizard
            lookup_id = data.get('data', {}).get('id') or False
            classification_name = data.get("data", {}).get("attributes", {}).get("product_classification_name")
            
            hs_code = ''
            for item in data.get('included', []):
                if item.get('type') == 'hs_lookup_item':
                    hs_code = item['attributes'].get('hs_code')
            
            if hs_code:
                self.write({
                    'hs_code': hs_code[:6],
                    'lookup_id': lookup_id,
                    'is_generated': True,
                    'product_classification_name': classification_name or '',
                    'yarn_product_name': description if self.product_category == 'yarn' else self.yarn_product_name
                })
                return True
        except Exception as e:
            _logger.error("Failed to auto-generate HS code for product %s: %s", self.name, str(e))
        
        return False

