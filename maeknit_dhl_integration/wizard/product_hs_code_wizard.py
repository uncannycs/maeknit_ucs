# -*- coding: utf-8 -*-
import logging
import requests
import json
from lxml import etree
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class ProductHSCodeWizard(models.TransientModel):
    _name = 'product.hs.code.wizard'
    _description = 'HS Code Generation Wizard'

    product_id = fields.Many2one('product.product', string="Product", readonly=True)
    product_name = fields.Char(string="Product Name/Description", required=True)
    country_code_id = fields.Many2one('res.country', string="Origin Country", required=True)
    country_code = fields.Char(string="Country Code", readonly=True)
    hs_code = fields.Char(string="HS Code")
    purchase_order_id = fields.Many2one('purchase.order', string="Purchase Order")
    is_generated = fields.Boolean(string="Is HS Code Generated", default=False)
    product_classification_name = fields.Char(string="Hs Code Description", readonly=True)

    @api.onchange('country_code_id')
    def _onchange_country_code(self):
        for rec in self:
            if rec.country_code_id:
                rec.country_code = rec.country_code_id.code
            else:
                rec.country_code = None


    @api.model
    def default_get(self, fields):
        res = super(ProductHSCodeWizard, self).default_get(fields)
        if self._context.get('active_model') == 'purchase.order.line':
            line = self.env['purchase.order.line'].browse(self._context.get('active_id'))
            if line.product_id:
                product = line.product_id
                product_name = ''

                if product.product_category == 'yarn':
                    # Priority 1: Use direct field if already populated
                    if product.yarn_product_name:
                        product_name = product.yarn_product_name
                    else:
                        # Priority 2: Use composition format [Fibers] [Category] [Purpose]
                        fiber_parts = [f"{f.percentage}% {f.fiber_type_id.name}" for f in product.fiber_ids]
                        fibers_str = " ".join(fiber_parts)
                        
                        product_category_labels = dict(product.fields_get(['product_category'])['product_category']['selection'])
                        category_label = product_category_labels.get(product.product_category, '')
                        
                        shipment_purpose_labels = dict(line.order_id.fields_get(['shipment_purpose'])['shipment_purpose']['selection'])
                        shipment_purpose_label = shipment_purpose_labels.get(line.order_id.shipment_purpose, '')
                        
                        name_parts = [p for p in [fibers_str, category_label, shipment_purpose_label] if p]
                        product_name = " ".join(name_parts) if name_parts else ''

                res.update({
                    'product_id': product.id,
                    'product_name': product_name,
                    'purchase_order_id':line.order_id.id,
                    'country_code_id': line.order_id.partner_id.country_id.id,
                    'hs_code': product.hs_code if product.hs_code else '',
                    'is_generated': line.is_generated if line.is_generated else False,
                    'product_classification_name': product.product_classification_name if product.product_classification_name else '',
                })
        return res

    def action_generate_dhl_hs_code(self):
        self.ensure_one()

        company = self.env.company

        if company and company.dutify_api_key:
            api_key = company.dutify_api_key
        else:
            raise ValidationError(_("Please enter your Dutify API key"))

        url = "https://dutify.com/api/v1/hs_lookups"

        payload = {"data": {
            "description": self.product_name,
            "country_code": self.country_code_id.code,
        }}

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "X-API-KEY": api_key
        }
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()

        # ✅ ERROR HANDLING
        if isinstance(data.get('data'), list):
            error_data = data['data'][0] if data['data'] else {}
            error_msg = error_data.get('attributes', {}).get('message', 'Unknown API Error')
            raise ValidationError(_("Dutify Error: %s") % error_msg)

        lookup_id = data.get('data', {}).get('id') or False
        classification_name = data.get("data", {}).get("attributes", {}).get("product_classification_name")

        hs_code = ''

        for item in data.get('included', []):
            if item.get('type') == 'hs_lookup_item':
                hs_code = item['attributes'].get('hs_code')

        if hs_code:

            self.hs_code = hs_code[:6]
            self.product_classification_name = classification_name if classification_name else ''

            # ✅ SET BOOLEAN TRUE
            country_of_origin_id = self.env['res.country'].search([('code', '=', self.country_code_id.code)], limit=1)

            if self.product_id and self.hs_code:
                self.product_id.is_generated = True
                self.product_id.lookup_id = lookup_id
                self.product_id.hs_code = self.hs_code
                self.product_id.country_of_origin = country_of_origin_id.id if country_of_origin_id else False
                self.product_id.product_classification_name = classification_name if classification_name else ''
                if self.product_id.product_category == 'yarn':
                    self.product_id.yarn_product_name = self.product_name


            return {
                'type': 'ir.actions.act_window',
                'res_model': 'product.hs.code.wizard',
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }


    def action_apply_hs_code(self):
        self.ensure_one()
        if self.product_id and self.hs_code:
            self.product_id.write({'hs_code': self.hs_code})
            if self.country_code_id:
                country_of_origin_id = self.env['res.country'].search([('code', '=', self.country_code_id.code)], limit=1)
                if country_of_origin_id:
                    self.product_id.write({'country_of_origin': country_of_origin_id.id})
            return {'type': 'ir.actions.act_window_close'}
        return {'type': 'ir.actions.act_window_close'}
