import base64
import json
import logging
import time
from datetime import datetime
from requests import request
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    def init(self):
        """Ensure ShipStation carriers stay active after DB restores / server restarts."""
        super().init()
        try:
            self.env.cr.execute("""
                UPDATE delivery_carrier
                SET active = true
                WHERE delivery_type = 'shipstation' AND active = false
            """)
            if self.env.cr.rowcount:
                logging.info("Auto-activated %d archived ShipStation carrier(s).", self.env.cr.rowcount)
        except Exception:
            logging.info("Could not check ShipStation carrier active state.")

    shipstation_carrier_id = fields.Many2one('shipstation.delivery.carrier', string='Shipstation Carrier')
    shipstation_delivery_carrier_service_id = fields.Many2one('shipstation.delivery.carrier.service',
                                                              string='Shipstation Delivey Carrier Service')
    delivery_type = fields.Selection(selection_add=[('shipstation', 'Shipstation')],
                                     ondelete={'shipstation': 'set default'})
    delivery_package_id = fields.Many2one('shipstation.delivery.package', string='Shipstation Package Code')
    height = fields.Float(related="delivery_package_id.height", readonly=False)
    width = fields.Float(related="delivery_package_id.width", readonly=False)
    length = fields.Float(related="delivery_package_id.length", readonly=False)
    weight_uom = fields.Selection([('pounds', 'pounds'), ('ounces', 'ounces'), ('grams', 'grams')], default="pounds",
                                  string='Weight UOM')
    shipstation_dimentions = fields.Selection([('inches', 'inches'), ('centimeters', 'centimeters')], default="inches",
                                              string='Shipstation Dimentions')
    confirmation = fields.Selection(
        [('none', 'None'), ('delivery', 'Delivery'), ('signature', 'Signature'), ('adult_signature', 'adult_signature'),
         ('direct_signature', 'direct_signature')], default="none",
        string='Shipstation Confirmation')
    store_id = fields.Many2one('shipstation.store.vts', "Store")
    shipstation_configuration_id = fields.Many2one('shipstation.odoo.configuration.vts',
                                                   string='Shipstation Configuration')

    def get_total_weight(self, weight=1):
        pound_for_kg = 2.20462
        ounce_for_kg = 35.274
        grams_for_kg = 1000
        ounce_for_lb = 16
        grams_for_lb = 453.592
        uom_id = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        if self.weight_uom == "pounds" and uom_id.name in ['lb', 'lbs']:
            return round(weight, 3)
        elif self.weight_uom == "pounds" and uom_id.name == 'kg':
            return round(weight * pound_for_kg, 3)
        elif self.weight_uom == "ounces" and uom_id.name in ['lb', 'lbs']:
            return round(weight * ounce_for_lb, 3)
        elif self.weight_uom == "ounces" and uom_id.name == 'kg':
            return round(weight * ounce_for_kg, 3)
        elif self.weight_uom == "grams" and uom_id.name == 'kg':
            return round(weight * grams_for_kg, 3)
        else:
            return round(weight * grams_for_lb, 3)

    def check_order_data(self, order):
        lines_without_weight = order.order_line.filtered(
            lambda line_item: not line_item.product_id.type in ['service',
                                                                'digital'] and not line_item.product_id.weight and not line_item.is_delivery)
        for order_line in lines_without_weight:
            return _("Please define weight in product : \n %s") % order_line.product_id.name
        receiver_address = order.partner_shipping_id
        sender_address = order.warehouse_id.partner_id
        if not receiver_address.zip or not receiver_address.country_id or not receiver_address.city:
            return _("Please define proper receiver address.")
        if not sender_address.zip or not sender_address.country_id or not sender_address.city:
            return _("Please define proper Sender address.")

        return False

    def _is_v2_enabled(self):
        """Check if V2 API is enabled on the linked configuration."""
        config = self.shipstation_configuration_id
        return config and config.use_v2_api and config.api_key_v2

    def api_calling_function(self, url_data, body):
        url = self.shipstation_configuration_id.making_shipstation_url(url_data)
        api_secret = self.shipstation_configuration_id.api_secret
        api_key = self.shipstation_configuration_id.api_key
        data = "%s:%s" % (api_key, api_secret)
        encode_data = base64.b64encode(data.encode("utf-8"))
        authrization_data = "Basic %s" % (encode_data.decode("utf-8"))
        headers = {"Authorization": authrization_data,
                   "Content-Type": "application/json"}
        data = json.dumps(body)
        logging.info(" Custom Code:Request Data: %s" % (data))
        try:
            response_body = request(method='POST', url=url, data=data, headers=headers)
        except Exception as e:
            raise ValidationError(e)
        return response_body

    def api_calling_function_v2(self, url_data, body=None, method='POST'):
        """Make a V2 API call using the API-Key header."""
        config = self.shipstation_configuration_id
        url = config.making_shipstation_url_v2(url_data)
        headers = {
            "API-Key": config.api_key_v2,
            "Content-Type": "application/json",
        }
        data = json.dumps(body) if body else None
        logging.info("V2 API Request: %s %s body=%s", method, url, data)
        try:
            response_body = request(method=method, url=url, data=data, headers=headers)
        except Exception as e:
            raise ValidationError(e)
        return response_body

    # ── V2 helpers ──────────────────────────────────────────────

    def _v2_weight_unit(self):
        """Convert V1 weight unit names to V2 singular form."""
        mapping = {'pounds': 'pound', 'ounces': 'ounce', 'grams': 'gram'}
        return mapping.get(self.weight_uom, 'pound')

    def _v2_dimension_unit(self):
        """Convert V1 dimension unit names to V2 singular form."""
        mapping = {'inches': 'inch', 'centimeters': 'centimeter'}
        return mapping.get(self.shipstation_dimentions, 'inch')

    def _v2_residential_indicator(self, is_residential=False):
        return "yes" if is_residential else "no"

    # Known aliases between V1 and V2 carrier codes (same as config model).
    _V1_V2_CODE_ALIASES = {
        'stamps_com': 'usps',
        'usps': 'stamps_com',
        'ups_walleted': 'ups',
        'ups': 'ups_walleted',
        'fedex': 'fedex_walleted',
        'fedex_walleted': 'fedex',
        'dhl_express_worldwide': 'dhl_express',
        'dhl_express': 'dhl_express_worldwide',
    }

    def _get_v2_carrier_ids(self, carrier_code=None):
        """Resolve V2 carrier_ids from carrier code(s).
        Tries exact match first, then suffix variants, then known aliases."""
        config_id = self.shipstation_configuration_id.id
        carrier_obj = self.env['shipstation.delivery.carrier']

        if not carrier_code:
            carriers = carrier_obj.search([('shipstation_configuration_id', '=', config_id)])
            result = [c.v2_carrier_id for c in carriers if c.v2_carrier_id]
            logging.info("_get_v2_carrier_ids(no code filter): found %d v2 IDs from %d carriers", len(result), len(carriers))
            return result

        # Step 1: Exact code match
        carriers = carrier_obj.search([
            ('shipstation_configuration_id', '=', config_id),
            ('code', '=', carrier_code),
        ])
        result = [c.v2_carrier_id for c in carriers if c.v2_carrier_id]
        if result:
            logging.info("_get_v2_carrier_ids('%s'): exact match → %s", carrier_code, result)
            return result
        logging.info("_get_v2_carrier_ids('%s'): no exact match (carriers found: %s)",
                      carrier_code, [(c.code, c.v2_carrier_id) for c in carriers])

        # Step 2: Try suffix variants (_walleted, _ltl_walleted, strip suffix)
        suffix_variants = set()
        for suffix in ['_walleted', '_ltl_walleted']:
            suffix_variants.add(carrier_code + suffix)
            if carrier_code.endswith(suffix):
                suffix_variants.add(carrier_code[:-len(suffix)])
        for variant in suffix_variants:
            carriers = carrier_obj.search([
                ('shipstation_configuration_id', '=', config_id),
                ('code', '=', variant),
            ])
            result = [c.v2_carrier_id for c in carriers if c.v2_carrier_id]
            if result:
                logging.info("_get_v2_carrier_ids('%s'): suffix variant '%s' → %s", carrier_code, variant, result)
                return result

        # Step 3: Try known alias (stamps_com → usps, ups_walleted → ups, etc.)
        alias = self._V1_V2_CODE_ALIASES.get(carrier_code)
        if alias:
            carriers = carrier_obj.search([
                ('shipstation_configuration_id', '=', config_id),
                ('code', '=', alias),
            ])
            result = [c.v2_carrier_id for c in carriers if c.v2_carrier_id]
            if result:
                logging.info("_get_v2_carrier_ids('%s'): alias '%s' → %s", carrier_code, alias, result)
                return result
            # Also try alias + suffix variants
            for suffix in ['_walleted', '_ltl_walleted']:
                for av in [alias + suffix, alias[:-len(suffix)] if alias.endswith(suffix) else None]:
                    if av:
                        carriers = carrier_obj.search([
                            ('shipstation_configuration_id', '=', config_id),
                            ('code', '=', av),
                        ])
                        result = [c.v2_carrier_id for c in carriers if c.v2_carrier_id]
                        if result:
                            logging.info("_get_v2_carrier_ids('%s'): alias variant '%s' → %s", carrier_code, av, result)
                            return result

        # Step 4: Last resort - search ALL carriers with v2_carrier_id and log them for debugging
        all_with_v2 = carrier_obj.search([
            ('shipstation_configuration_id', '=', config_id),
            ('v2_carrier_id', '!=', False),
        ])
        logging.warning("_get_v2_carrier_ids('%s'): NO MATCH FOUND. All V1 carriers with v2_carrier_id: %s",
                         carrier_code, [(c.code, c.v2_carrier_id, c.name) for c in all_with_v2])
        return []
    
    def shipstation_rate_shipment_picking(self, picking, carrier_code=None, residential=False, package_id=None):
        """Fetch rates for a picking. Uses V2 for USPS/UPS/FedEx when enabled, V1 otherwise."""
        v2_enabled = self._is_v2_enabled()
        logging.info(
            "=== RATE REQUEST === carrier_code=%s, v2_enabled=%s, picking=%s, package=%s",
            carrier_code, v2_enabled, picking.name, package_id.id if package_id else False,
        )
        if v2_enabled:
            try:
                result = self._shipstation_rate_shipment_picking_v2(
                    picking, carrier_code=carrier_code, residential=residential, package_id=package_id
                )
                if result.get('success'):
                    logging.info("V2 rate fetch SUCCEEDED for carrier_code=%s", carrier_code)
                    return result
                logging.warning("V2 rate fetch FAILED for carrier_code=%s: %s", carrier_code, result.get('error_message'))
            except Exception as e:
                logging.warning("V2 rate fetch EXCEPTION for carrier_code=%s: %s", carrier_code, e)
        return self._shipstation_rate_shipment_picking_v1(
            picking, carrier_code=carrier_code, residential=residential, package_id=package_id
        )

    def _resolve_rate_package_code(self, picking, package_id):
        if package_id and hasattr(package_id, "shipstation_delivery_package_id") and package_id.shipstation_delivery_package_id:
            return package_id.shipstation_delivery_package_id.package_code or ""
        if getattr(picking, "delivery_package_id", False):
            return picking.delivery_package_id.package_code or ""
        if self.delivery_package_id:
            return self.delivery_package_id.package_code or ""
        return ""

    def _resolve_rate_weight_kg(self, picking, package_id):
        """Return weight in Odoo's base weight uom (kg in most DBs)."""
        if package_id:
            if getattr(package_id, "shipping_weight", 0.0):
                return package_id.shipping_weight
            if getattr(package_id, "weight", 0.0):
                return package_id.weight
            if getattr(package_id, "minimum_weight", 0.0):
                return package_id.minimum_weight
            # last fallback: compute from quants (uses product weight)
            try:
                total = 0.0
                for quant in package_id.quant_ids:
                    total += quant.quantity * (quant.product_id.weight or 0.0)
                if total:
                    return total
            except Exception:
                pass

        return sum(
            (line.product_id.weight * line.product_uom_qty)
            for line in picking.move_ids
            if line.product_id.type not in ['service', 'digital']
        )

    def _resolve_rate_dimensions(self, picking, package_id):
        return {
            "length": self._resolve_label_dimension(picking, package_id, "length"),
            "width": self._resolve_label_dimension(picking, package_id, "width"),
            "height": self._resolve_label_dimension(picking, package_id, "height"),
        }

    def _shipstation_rate_shipment_picking_v1(self, picking, carrier_code=None, residential=False, package_id=None):
        """Original V1 rate fetching logic."""
        shipping_charge_obj = self.env['shipstation.shipping.charge']

        receiver = picking.partner_id
        sender = picking.picking_type_id.warehouse_id.partner_id

        if not receiver.zip or not receiver.country_id or not receiver.city:
            return {'success': False, 'error_message': "Incomplete receiver address."}

        weight_kg = self._resolve_rate_weight_kg(picking, package_id)
        total_weight = self.get_total_weight(weight_kg)

        if carrier_code:
            carrier_to_use = carrier_code
        else:
            carrier = picking.shipstation_carrier_id or self.shipstation_carrier_id
            if not carrier:
                return {'success': False, 'error_message': "Please select a ShipStation Carrier first."}
            carrier_to_use = carrier.code

        dims = self._resolve_rate_dimensions(picking, package_id)
        package_code = self._resolve_rate_package_code(picking, package_id)
        logging.info(
            "RATE INPUT resolved: package_code=%s weight_kg=%s total_weight=%s dims=%s (picking=%s package=%s)",
            package_code,
            weight_kg,
            total_weight,
            dims,
            picking.id,
            package_id.id if package_id else False,
        )

        dict_rate = {
            "carrierCode": carrier_to_use,
            "fromCountry": "US",
            "packageCode": package_code,
            "fromPostalCode": sender.zip,
            "toState": receiver.state_id.code or "",
            "toCountry": receiver.country_id.code,
            "toPostalCode": receiver.zip,
            "toCity": receiver.city,
            "weight": {
                "value": total_weight,
                "units": self.weight_uom
            },
            "dimensions": {
                "units": self.shipstation_dimentions,
                "length": dims.get('length', 0.0),
                "width": dims.get('width', 0.0),
                "height": dims.get('height', 0.0),
            },
            "confirmation": self.confirmation,
            "residential": bool(residential),
        }
        logging.info('V1 dict rate %s', dict_rate)

        response_data = self.api_calling_function("/shipments/getrates", dict_rate)
        logging.info('ShipStation V1 rate response: %s', response_data)
        if response_data.status_code != 200:
            return {'success': False, 'error_message': response_data.text}

        responses = response_data.json()
        if not responses:
            return {'success': False, 'error_message': "No rates returned."}
        logging.info('ShipStation V1 rate responses: %s', responses)

        for r in responses:
            shipping_charge_obj.create({
                'shipstation_provider': carrier_to_use,
                'shipstation_service_code': r.get('serviceCode'),
                'shipstation_service_name': r.get('serviceName'),
                'shipping_cost': r.get('shipmentCost', 0.0),
                'other_cost': r.get('otherCost', 0.0),
                'picking_id': picking.id,
            })

        return {'success': True}

    def _shipstation_rate_shipment_picking_v2(self, picking, carrier_code=None, residential=False, package_id=None):
        """V2 rate fetching: POST /v2/rates."""
        shipping_charge_obj = self.env['shipstation.shipping.charge']

        receiver = picking.partner_id
        sender = picking.picking_type_id.warehouse_id.partner_id

        if not receiver.zip or not receiver.country_id or not receiver.city:
            return {'success': False, 'error_message': "Incomplete receiver address."}

        weight_kg = self._resolve_rate_weight_kg(picking, package_id)
        total_weight = self.get_total_weight(weight_kg)

        # Resolve V2 carrier IDs
        v2_carrier_ids = self._get_v2_carrier_ids(carrier_code)
        if not v2_carrier_ids:
            return {'success': False, 'error_message': "No V2 carrier ID found for '%s'. Please re-import carriers." % carrier_code}

        dims = self._resolve_rate_dimensions(picking, package_id)
        package_code = self._resolve_rate_package_code(picking, package_id)
        logging.info(
            "RATE INPUT resolved (V2): package_code=%s weight_kg=%s total_weight=%s dims=%s (picking=%s package=%s)",
            package_code,
            weight_kg,
            total_weight,
            dims,
            picking.id,
            package_id.id if package_id else False,
        )

        v2_body = {
            "rate_options": {
                "carrier_ids": v2_carrier_ids,
            },
            "shipment": {
                "validate_address": "no_validation",
                "ship_to": {
                    "name": receiver.name or "",
                    "company_name": receiver.parent_id.name if receiver.parent_id else "",
                    "phone": receiver.phone or "",
                    "address_line1": receiver.street or "",
                    "address_line2": receiver.street2 or "",
                    "city_locality": receiver.city or "",
                    "state_province": receiver.state_id.code if receiver.state_id else "",
                    "postal_code": receiver.zip or "",
                    "country_code": receiver.country_id.code if receiver.country_id else "US",
                    "address_residential_indicator": self._v2_residential_indicator(residential),
                },
                "ship_from": {
                    "name": sender.name or "",
                    "company_name": sender.parent_id.name if sender.parent_id else "",
                    "phone": sender.phone or "",
                    "address_line1": sender.street or "",
                    "address_line2": sender.street2 or "",
                    "city_locality": sender.city or "",
                    "state_province": sender.state_id.code if sender.state_id else "",
                    "postal_code": sender.zip or "",
                    "country_code": sender.country_id.code if sender.country_id else "US",
                    "address_residential_indicator": "no",
                },
                "packages": [
                    {
                        "weight": {
                            "value": total_weight,
                            "unit": self._v2_weight_unit(),
                        },
                        "dimensions": {
                            "unit": self._v2_dimension_unit(),
                            "length": dims.get('length', 0.0),
                            "width": dims.get('width', 0.0),
                            "height": dims.get('height', 0.0),
                        },
                    }
                ],
            },
        }
        logging.info('V2 rate request body: %s', v2_body)

        response_data = self.api_calling_function_v2("/v2/rates", v2_body)
        logging.info('ShipStation V2 rate response status: %s', response_data.status_code)

        if response_data.status_code != 200:
            return {'success': False, 'error_message': "V2 rates error: %s" % response_data.text}

        resp_json = response_data.json()
        rates = resp_json.get('rate_response', resp_json).get('rates', []) if isinstance(resp_json, dict) else []
        if not rates:
            # Try top-level 'rates' key
            rates = resp_json.get('rates', [])
        if not rates:
            return {'success': False, 'error_message': "V2 returned no rates."}

        logging.info('ShipStation V2 rates count: %d', len(rates))

        for r in rates:
            # V2 monetary values are objects {currency, amount}
            shipping_amount = r.get('shipping_amount', {})
            other_amount = r.get('other_amount', {})
            shipping_cost = shipping_amount.get('amount', 0.0) if isinstance(shipping_amount, dict) else 0.0
            other_cost = other_amount.get('amount', 0.0) if isinstance(other_amount, dict) else 0.0

            shipping_charge_obj.create({
                'shipstation_provider': r.get('carrier_code', carrier_code or ''),
                'shipstation_service_code': r.get('service_code', ''),
                'shipstation_service_name': r.get('service_type', ''),
                'shipping_cost': shipping_cost,
                'other_cost': other_cost,
                'picking_id': picking.id,
                'v2_rate_id': r.get('rate_id', ''),
            })

        return {'success': True}


    def shipstation_rate_shipment(self, order):
        checked_order_data = self.check_order_data(order)
        shipping_charge_obj = self.env['shipstation.shipping.charge']
        if checked_order_data:
            return {'success': False, 'price': 0.0, 'error_message': checked_order_data,
                    'warning_message': False}
        receiver_address = order.partner_shipping_id
        sender_address = order.warehouse_id.partner_id

        weight = sum(
            [(line.product_id.weight * line.product_uom_qty) for line in order.order_line if not line.is_delivery])
        total_weight = self.get_total_weight(weight)
        if not self._context.get('order_weight'):
            total_weight = self.get_total_weight(weight)
        else:
            total_weight = self._context.get('order_weight')
        dict_rate = {
            "carrierCode": "%s" % (
                    self.shipstation_carrier_id and self.shipstation_carrier_id.code),
            "packageCode": "%s" % (self.delivery_package_id and self.delivery_package_id.package_code),
            "fromPostalCode": "%s" % (sender_address.zip),
            "toState": "%s" % (receiver_address.state_id and receiver_address.state_id.code),
            "toCountry": "%s" % (receiver_address.country_id and receiver_address.country_id.code),
            "toPostalCode": "%s" % (receiver_address.zip),
            "toCity": receiver_address.city,
            "weight": {
                "value": total_weight,
                "units": self.weight_uom or "pounds"
            },
            "dimensions": {
                "units": self.shipstation_dimentions or "inches",
                "length": self.delivery_package_id and self.delivery_package_id.length or 0.0,
                "width": self.delivery_package_id and self.delivery_package_id.width or 0.0,
                "height": self.delivery_package_id and self.delivery_package_id.height or 0.0
            },
            "confirmation": self.confirmation or "none",
            "residential": self.shipstation_delivery_carrier_service_id and self.shipstation_delivery_carrier_service_id.residential_address
        }
        
        logging.info('dict rate %s', dict_rate)

        # is_website = self.env['ir.module.module'].search([('name', '=', 'website_sale')])
        # if is_website and is_website.state == 'installed' and order.website_id:
        #     dict_rate.update({
        #         "serviceCode": "%s" % (
        #                 self.shipstation_delivery_carrier_service_id and self.shipstation_delivery_carrier_service_id.service_code),
        #     })
        # else:
        # existing_records = self.env['shipstation.shipping.charge'].search(
        #     [('sale_order_id', '=', order and order.id)])
        # if existing_records:
        #     existing_records.sudo().unlink()
        try:
            response_data = self.api_calling_function("/shipments/getrates", dict_rate)
            logging.info('ShipStation rate response: %s', response_data)
            if response_data.status_code == 200:
                responses = response_data.json()
                logging.info(" Custom Code:Response Data: %s" % (responses))
                # if is_website and is_website.state == 'installed' and order.website_id:
                #     for rate in responses:
                #         is_service_available = self.shipstation_delivery_carrier_service_id.search(
                #             [("service_code", '=', rate.get('serviceCode'))])
                #         if is_service_available:
                #             return {'success': True, 'price': rate.get('shipmentCost') or 0.0,
                #                     'error_message': False, 'warning_message': False}
                #         else:
                #             return {'success': False, 'price': 0.0, 'error_message': "Service is not available.",
                #                     'warning_message': False}
                # self._cr.commit()
                if responses:
                    rate_datas = []
                    for response in responses:
                        if not shipping_charge_obj.search([('sale_order_id', '=', order and order.id), (
                        'shipstation_service_name', '=', response.get('serviceName')), ('shipping_cost', '=',response.get('shipmentCost')),('shipstation_service_code', '=',response.get('serviceCode'))]):
                            rate_datas.append(
                                {'shipstation_provider': self.shipstation_carrier_id.code,
                                 'shipstation_service_code': response.get('serviceCode'),
                                 'shipstation_service_name': response.get('serviceName'),
                                 'shipping_cost': response.get('shipmentCost', 0.0),
                                 'other_cost': response.get('otherCost', 0.0),
                                 'sale_order_id': order and order.id})
                        self._cr.commit()
                    shipping_charge_obj.sudo().create(rate_datas)
                    shipstation_charge_id = self.env['shipstation.shipping.charge'].search(
                        [('sale_order_id', '=', order and order.id),
                         ('shipstation_service_code', '=', self.shipstation_delivery_carrier_service_id.service_code)],
                        limit=1)
                    if not shipstation_charge_id:
                        shipstation_charge_id = self.env['shipstation.shipping.charge'].search(
                            [('sale_order_id', '=', order and order.id),
                             ('shipstation_provider', '=', self.shipstation_carrier_id.code)], order='shipping_cost',
                            limit=1)
                    order.shipstation_shipping_charge_id = shipstation_charge_id and shipstation_charge_id.id
                    rate_amount = shipstation_charge_id.shipping_cost + shipstation_charge_id.other_cost
                    return {'success': True, 'price': rate_amount or 0.0,
                            'error_message': False, 'warning_message': False}
                else:
                    return {'success': False, 'price': 0.0, 'error_message': "Service Not Supported.",
                            'warning_message': False}

            elif response_data.status_code == 500:
                error_message_details = ""
                if response_data.json():
                    error_response_data = response_data.json()
                    error_message_details = error_response_data.get('ExceptionMessage')
                return {'success': False, 'price': 0.0,
                        'error_message': "%s" % (error_message_details),
                        'warning_message': False}
            else:
                error_code = "%s" % (response_data.status_code)
                error_message = response_data.reason
                error_detail = {'error': error_code + " - " + error_message + " - "}
                return {'success': False, 'price': 0.0, 'error_message': error_detail,
                        'warning_message': False}
        except Exception as e:
            return {'success': False, 'price': 0.0, 'error_message': e,
                    'warning_message': False}

    def _resolve_label_dimension(self, picking, package_id, field_name):
        """Resolve dimension value: package own fields > picking > package type > carrier default."""
        # Package-specific dimensions first (custom fields on stock.quant.package)
        if package_id:
            pkg_value = getattr(package_id, field_name, False)
            if pkg_value:
                return pkg_value
        # Then picking-level dimensions
        pick_value = getattr(picking, field_name, False)
        if pick_value:
            return pick_value
        # Then package type defaults
        if package_id and package_id.package_type_id:
            return getattr(package_id.package_type_id, field_name, 0.0) or 0.0
        # Finally carrier default package
        if self.delivery_package_id:
            return getattr(self.delivery_package_id, field_name, 0.0) or 0.0
        return 0.0

    def generate_label_from_shipstation(self, picking, package_id=False, weight=False, shipstation_charge=None):
        """Build V1 label request data (unchanged logic)."""
        picking_receiver_id = picking.partner_id
        picking_sender_id = picking.picking_type_id.warehouse_id.partner_id
        shipstation_charge = shipstation_charge or picking.shipstation_shipping_charge_id or (
            picking.sale_id.shipstation_shipping_charge_id if picking.sale_id else None)
        carrier_code = shipstation_charge and shipstation_charge.shipstation_provider or (
            self.shipstation_carrier_id and self.shipstation_carrier_id.code)
        fallback_carrier_code = self.shipstation_carrier_id and self.shipstation_carrier_id.code
        search_code = carrier_code or fallback_carrier_code
        shipstation_carrier_code = self.env['shipstation.delivery.carrier'].search(
            [('code', '=', search_code)])

        package_length = self._resolve_label_dimension(picking, package_id, "length")
        shipstation_shipping_charge_id = shipstation_charge or picking.sale_id.shipstation_shipping_charge_id
        shipstation_service_code = shipstation_shipping_charge_id.shipstation_service_code if shipstation_shipping_charge_id else picking.carrier_id.shipstation_delivery_carrier_service_id.service_code
        total_weight = self.get_total_weight(weight)
        # Prefer explicitly selected ShipStation package code on the package/picking.
        package_code = ""
        package_code_source = "none"
        if package_id and hasattr(package_id, "shipstation_delivery_package_id") and package_id.shipstation_delivery_package_id:
            package_code = package_id.shipstation_delivery_package_id.package_code or ""
            package_code_source = "package.shipstation_delivery_package_id"
        elif getattr(picking, "delivery_package_id", False):
            package_code = picking.delivery_package_id.package_code or ""
            package_code_source = "picking.delivery_package_id"
        elif package_id and getattr(package_id, "package_type_id", False) and getattr(package_id.package_type_id, "shipper_package_code", False):
            package_code = package_id.package_type_id.shipper_package_code or ""
            package_code_source = "package.package_type_id.shipper_package_code"
        elif self.delivery_package_id:
            package_code = self.delivery_package_id.package_code or ""
            package_code_source = "carrier.delivery_package_id"

        logging.info(
            "ShipStation packageCode resolved: %s (source=%s, picking=%s, package=%s)",
            package_code, package_code_source, picking.id, package_id.id if package_id else False,
        )

        request_data = {
            "orderId": "%s" % (picking.shipstation_order_id),
            "carrierCode": "%s" % (carrier_code),
            "serviceCode": "%s" % (shipstation_service_code),
            "packageCode": "%s" % (package_code),
            "confirmation": self.confirmation or "none",
            "shipDate": "%s" % (time.strftime("%Y-%m-%d")),
            "testLabel": False,
            "weight": {
                "value": total_weight,
                "units": self.weight_uom or "pounds",
            },
            "dimensions": {
                "units": self.shipstation_dimentions or "inches",
                "length": package_length or 0.0,
                "width": self._resolve_label_dimension(picking, package_id, "width"),
                "height": self._resolve_label_dimension(picking, package_id, "height"),
            },
        }
        logging.info(" Custom Code:Label Request Data: %s" % (request_data))
        if len(shipstation_carrier_code) > 1 and self.shipstation_carrier_id.shipping_provider_id:
            request_data.setdefault("advancedOptions", {}).update({
                "billToParty": "my_other_account",
                "billToMyOtherAccount": self.shipstation_carrier_id.shipping_provider_id,
            })
        logging.info(" Custom Code:Request Data %s" %request_data)
        return request_data

    def generate_label_from_shipstation_v2(self, picking, package_id=False, weight=False, shipstation_charge=None):
        """Generate a label via V2 API. Uses rate_id if available, otherwise full shipment details."""
        shipstation_charge = shipstation_charge or picking.shipstation_shipping_charge_id or (
            picking.sale_id.shipstation_shipping_charge_id if picking.sale_id else None)

        total_weight = self.get_total_weight(weight)

        # If we have a V2 rate_id, use the simpler rate-based label endpoint
        if shipstation_charge and shipstation_charge.v2_rate_id:
            endpoint = "/v2/labels/rates/%s" % shipstation_charge.v2_rate_id
            body = {
                "label_format": "pdf",
                "label_layout": "4x6",
                "label_download_type": "inline",
            }
            logging.info("V2 label from rate_id: %s", shipstation_charge.v2_rate_id)
            response_data = self.api_calling_function_v2(endpoint, body)
            return response_data

        # No rate_id — use full shipment details via POST /v2/labels
        receiver = picking.partner_id
        sender = picking.picking_type_id.warehouse_id.partner_id
        carrier_code = shipstation_charge and shipstation_charge.shipstation_provider or (
            self.shipstation_carrier_id and self.shipstation_carrier_id.code)
        service_code = shipstation_charge.shipstation_service_code if shipstation_charge else (
            self.shipstation_delivery_carrier_service_id.service_code if self.shipstation_delivery_carrier_service_id else "")

        # Resolve V2 carrier ID
        v2_carrier_ids = self._get_v2_carrier_ids(carrier_code)
        v2_carrier_id = v2_carrier_ids[0] if v2_carrier_ids else ""

        body = {
            "label_format": "pdf",
            "label_layout": "4x6",
            "label_download_type": "inline",
            "shipment": {
                "carrier_id": v2_carrier_id,
                "service_code": service_code,
                "ship_date": time.strftime("%Y-%m-%d"),
                "ship_to": {
                    "name": receiver.name or "",
                    "company_name": receiver.parent_id.name if receiver.parent_id else "",
                    "phone": receiver.phone or "",
                    "address_line1": receiver.street or "",
                    "address_line2": receiver.street2 or "",
                    "city_locality": receiver.city or "",
                    "state_province": receiver.state_id.code if receiver.state_id else "",
                    "postal_code": receiver.zip or "",
                    "country_code": receiver.country_id.code if receiver.country_id else "US",
                },
                "ship_from": {
                    "name": sender.name or "",
                    "company_name": sender.parent_id.name if sender.parent_id else "",
                    "phone": sender.phone or "",
                    "address_line1": sender.street or "",
                    "address_line2": sender.street2 or "",
                    "city_locality": sender.city or "",
                    "state_province": sender.state_id.code if sender.state_id else "",
                    "postal_code": sender.zip or "",
                    "country_code": sender.country_id.code if sender.country_id else "US",
                },
                "packages": [
                    {
                        "weight": {
                            "value": total_weight,
                            "unit": self._v2_weight_unit(),
                        },
                        "dimensions": {
                            "unit": self._v2_dimension_unit(),
                            "length": self._resolve_label_dimension(picking, package_id, "length"),
                            "width": self._resolve_label_dimension(picking, package_id, "width"),
                            "height": self._resolve_label_dimension(picking, package_id, "height"),
                        },
                    }
                ],
            },
        }
        logging.info("V2 label full request: %s", body)
        response_data = self.api_calling_function_v2("/v2/labels", body)
        return response_data

    def get_single_unit_price(self, move_line, picking_id):
        mrp_module = self.env['ir.module.module'].search([('name', '=', 'mrp')])

        if mrp_module and mrp_module.state == 'installed':
            if move_line.bom_line_id and move_line.bom_line_id.bom_id:
                bom = move_line.bom_line_id.bom_id
                product_id = bom.product_id or bom.product_tmpl_id.product_variant_id

                find_sale_line_id = picking_id.sale_id.order_line.filtered(
                    lambda x: x.product_id.id == product_id.id and move_line.sale_line_id.id == x.id
                )
                find_sale_line_id = find_sale_line_id[:1]

                if find_sale_line_id:
                    unit_price = find_sale_line_id.price_subtotal / find_sale_line_id.product_uom_qty
                    kit_qty = sum(bom.bom_line_ids.mapped(
                        'product_qty')) or 1  # if not found kit qty then pass 1 because to avoid  division by 0 error
                    single_unit_price = unit_price / kit_qty
                else:
                    single_unit_price = 0.0
            else:
                product_id = move_line.product_id
                find_sale_line_id = picking_id.sale_id.order_line.filtered(
                    lambda x: x.product_id.id == product_id.id and move_line.sale_line_id.id == x.id
                )
                find_sale_line_id = find_sale_line_id[:1]

                single_unit_price = (
                    find_sale_line_id.price_unit if find_sale_line_id else 0.0
                )
        else:
            product_id = move_line.product_id
            find_sale_line_id = picking_id.sale_id.order_line.filtered(
                lambda x: x.product_id.id == product_id.id and move_line.sale_line_id.id == x.id
            )
            find_sale_line_id = find_sale_line_id[:1]

            single_unit_price = (
                find_sale_line_id.price_unit if find_sale_line_id else 0.0
            )

        return find_sale_line_id, single_unit_price

    def get_order_item_details(self, picking):
        res = []
        count = 0
        for move_line in picking.move_ids:
            find_sale_line_id, single_unit_price = self.get_single_unit_price(move_line, picking)
            total_weight = self.get_total_weight(move_line.product_id.weight)
            count = count + 1
            item_dict = {
                "lineItemKey": "%s" % (count),
                "sku": "%s" % (move_line.product_id and move_line.product_id.default_code),
                "name": "%s" % (move_line.product_id and move_line.product_id.name),
                "weight": {
                    "value": "%s" % (total_weight),
                    "units": self.weight_uom or "pounds"
                },
                "quantity": int(move_line.product_uom_qty),
                "unitPrice": "%s" % (round(single_unit_price,2)),
                "taxAmount": "%s" % (round(move_line.sale_line_id.price_tax,2) if move_line.sale_line_id.price_tax else 0.0),
                "productId": "%s" % (move_line.product_id and move_line.product_id.id)}
            res.append(item_dict)
        return res

    def create_or_update_order(self, picking):
        if not self.store_id:
            raise ValidationError("Store Not Configured!")
        picking_receiver_id = picking.partner_id
        picking_sender_id = picking.picking_type_id.warehouse_id.partner_id
        total_value = picking.sale_id.amount_total if picking.sale_id.amount_total else sum(
            [(line.product_uom_qty * line.product_id.list_price) for line in picking.move_ids]) or 0.0
        warehouse_id = picking and picking.picking_type_id and picking.picking_type_id.warehouse_id and picking.picking_type_id.warehouse_id.shipstation_warehouse_id and picking.picking_type_id.warehouse_id.shipstation_warehouse_id.warehouse_id
        weight = picking.shipping_weight
        total_tax = picking.sale_id.amount_tax
        total_weight = self.get_total_weight(weight)
        shipstation_carrier_code = self.env['shipstation.delivery.carrier'].search(
            [('code', '=', self.shipstation_carrier_id.code)])
        date_order = picking.scheduled_date
        delivery_package_id = picking.delivery_package_id if picking.delivery_package_id else self.delivery_package_id
        if date_order:
            order_date_formate = datetime.strptime(str(date_order), "%Y-%m-%d %H:%M:%S")
            order_date = order_date_formate.strftime('%Y-%m-%dT%H:%M:%S')
            request_data = {
                "orderNumber": "%s" % (picking.origin if picking.origin else picking.name),
                "orderDate": "%s" % (order_date),
                "shipByDate": "%s" % (order_date),
                "orderStatus": "awaiting_shipment",
                "customerUsername": "%s" % (picking_receiver_id.name),
                "customerEmail": "%s" % (picking_receiver_id.email or ""),
                "billTo": {
                    "name": "%s" % (picking_receiver_id.name),
                    "company": "%s" % (picking_receiver_id.parent_id.name if picking_receiver_id.parent_id else ""),
                    "street1": "%s" % (picking_receiver_id.street or ""),
                    "street2": "%s" % (picking_receiver_id.street2 or ""),
                    "city": "%s" % (picking_receiver_id.city or ""),
                    "state": "%s" % (picking_receiver_id.state_id and picking_receiver_id.state_id.code or ""),
                    "postalCode": "%s" % (picking_receiver_id.zip or ""),
                    "country": "%s" % (picking_receiver_id.country_id and picking_receiver_id.country_id.code or ""),
                    "phone": "%s" % (picking_receiver_id.phone or ""),
                    "residential": self.shipstation_delivery_carrier_service_id and self.shipstation_delivery_carrier_service_id.residential_address
                },
                "shipTo": {
                    "name": "%s" % (picking_receiver_id.name),
                    "company": "%s" % (picking_receiver_id.parent_id.name if picking_receiver_id.parent_id else ""),
                    "street1": "%s" % (picking_receiver_id.street or ""),
                    "street2": "%s" % (picking_receiver_id.street2 or ""),
                    "city": "%s" % (picking_receiver_id.city or ""),
                    "state": "%s" % (picking_receiver_id.state_id and picking_receiver_id.state_id.code or ""),
                    "postalCode": "%s" % (picking_receiver_id.zip or ""),
                    "country": "%s" % (picking_receiver_id.country_id and picking_receiver_id.country_id.code or ""),
                    "phone": "%s" % (picking_receiver_id.phone or ""),
                    "residential": self.shipstation_delivery_carrier_service_id and self.shipstation_delivery_carrier_service_id.residential_address
                },
                "items": self.get_order_item_details(picking),
                "amountPaid": total_value,
                "taxAmount": total_tax,
                "shippingAmount": sum(
                    picking.sale_id.mapped('order_line').filtered(lambda line: line.is_delivery == True).mapped(
                        'price_subtotal')) or 0.0,
                "carrierCode": "%s" % (self.shipstation_carrier_id and self.shipstation_carrier_id.code),
                "serviceCode": "%s" % (
                        self.shipstation_delivery_carrier_service_id and self.shipstation_delivery_carrier_service_id.service_code),
                "packageCode": "%s" % (delivery_package_id and delivery_package_id.package_code or ""),
                "confirmation": self.confirmation or "none",
                "internalNotes": "{}".format(picking.note or ' '),
                "shipDate": "%s" % (order_date),
                "weight": {
                    "value": total_weight,
                    "units": "%s" % (self.weight_uom)
                },
                "dimensions": {
                    "units": "%s" % (self.shipstation_dimentions),
                    "length": delivery_package_id and delivery_package_id.length or 0.0,
                    "width": delivery_package_id and delivery_package_id.width or 0.0,
                    "height": delivery_package_id and delivery_package_id.height or 0.0,
                },
                "insuranceOptions": {
                    "provider": "%s" % (picking.shipstation_insurance_provider),
                    "insureShipment": picking.insureshipment,
                    "insuredValue": 200
                },
                # "internationalOptions": {
                #     "contents": picking.name,
                #     "customsItems": ""
                # },
                "advancedOptions": {
                    # TODO We need to send when import wh from shipstation "warehouseId": ,
                    "storeId": self.store_id and self.store_id.store_id or ""

                },
                "tagIds": [picking.id]
            }
            if warehouse_id:
                request_data.get('advancedOptions').update({"warehouseId": "{}".format(warehouse_id)})
            if len(shipstation_carrier_code) > 1 and self.shipstation_carrier_id.shipping_provider_id:
                request_data.get('advancedOptions').update({"billToParty": "my_other_account",
                                                            "billToMyOtherAccount": self.shipstation_carrier_id.shipping_provider_id})
        custom_items = []
        is_account_intrastat = self.env['ir.module.module'].search([('name', '=', 'account_intrastat')])
        if picking_sender_id and picking_receiver_id and picking_sender_id.country_id and picking_receiver_id.country_id and picking_sender_id.country_id.code != picking_receiver_id.country_id.code and is_account_intrastat and is_account_intrastat.state == 'installed':
            check_commodity = picking.move_line_ids.mapped('product_id').filtered(
                lambda produtct_id: not produtct_id.intrastat_code_id).mapped('name')
            if check_commodity:
                raise ValidationError("You Are Sending International Shipment \n But {} has no commodity code".format(
                    ', '.join(check_commodity)))
            check_origin_country = picking.move_line_ids.mapped('product_id').filtered(
                lambda produtct_id: not produtct_id.intrastat_origin_country_id).mapped('name')
            if check_origin_country:
                raise ValidationError(
                    "You Are Sending International Shipment \n But {} has no country origin code".format(
                        ', '.join(check_commodity)))
            for move in picking.move_ids:
                data = {
                    'description': "%s" % (move.product_id and move.product_id.name),
                    "quantity": "{}".format(int(move and move.product_uom_qty)),
                    "value": "{}".format(move.product_id and move.product_id.lst_price),
                    "harmonizedTariffCode": "{}".format(
                        move and move.product_id.intrastat_code_id and move.product_id.intrastat_code_id.code),
                    "countryOfOrigin": "{}".format(
                        move and move.product_id.intrastat_origin_country_id and move.product_id.intrastat_origin_country_id.code)
                }
                custom_items.append(data)
            if custom_items:
                request_data.update({
                    'internationalOptions': {
                        'contents': 'merchandise',
                        'customsItems': custom_items
                    }
                })
        return request_data

    @api.model
    def shipstation_send_shipping(self, pickings):
        for picking in pickings:
            if any(move.product_id.weight <= 0.0 for move in picking.move_ids):
                raise ValidationError("Need to set Product Weight.")
            if not picking.shipstation_order_id:
                body = self.create_or_update_order(picking)
                try:
                    response_data = self.api_calling_function("/orders/createorder", body)
                except Exception as error:
                    raise ValidationError(error)
                if response_data.status_code == 200:
                    responses = response_data.json()
                    logging.info(" Custom Code:Response Data: %s" % (responses))
                    order_id = responses.get('orderId')
                    order_key = responses.get('orderKey')
                    order_number = responses.get('orderNumber')
                    if order_id:
                        picking.write({'shipstation_order_id': order_id, 'shipstation_order_key': order_key,
                                       'shipstation_sale_order_number': order_number,
                                       'carrier_price': responses.get('shipmentCost', 0.0),
                                       'shipstation_configuration_id': self.shipstation_configuration_id.id})
                        if not (picking and picking.sale_id and picking.sale_id.shipstation_order_number):
                            picking.sale_id.shipstation_order_number = order_number
                            picking.sale_id.shipstation_order_id = order_id
                            picking.sale_id.shipstation_configuration_id = self.shipstation_configuration_id.id
                            picking.sale_id.is_exported_to_shipstation = True
                            picking.sale_id.shipstation_store_id = picking.carrier_id and picking.carrier_id.store_id.id
                    return [{'exact_price': 0.0, 'tracking_number': ''}]
                else:
                    error_code = "%s" % (response_data.status_code)
                    error_message = response_data.reason
                    error_detail = {'error': error_code + " - " + error_message + " - "}
                    # if response_data.json():
                    #     error_detail = {'error': error_code + " - " + error_message + " - %s" % (response_data.json())}
                    raise ValidationError("{}".format(error_detail))
            else:
                return [{'exact_price': 0.0, 'tracking_number': ''}]

    def shipstation_cancel_shipment(self, picking):
        shipment_id = picking.shipstation_shipment_id
        if not shipment_id:
            raise ValidationError("Shipstation Shipment Id Not Available!")
        req_data = {"shipmentId": '{}'.format(shipment_id)}
        try:
            response_data = self.api_calling_function("/shipments/voidlabel", req_data)
            if response_data.status_code == 200:
                responses = response_data.json()
                logging.info(" Custom Code:Response Data: %s" % (responses))
                approved = responses.get('approved')
                if approved:
                    picking.message_post(body=_('Shipment Cancelled In Shipstation %s' % (shipment_id)))
            else:
                error_code = "%s" % (response_data.status_code)
                error_message = response_data.reason
                error_detail = {'error': error_code + " - " + error_message + " - "}
                if response_data.json():
                    error_detail = {'error': error_code + " - " + error_message + " - %s" % (response_data.json())}
                raise ValidationError(error_detail)
        except Exception as e:
            raise ValidationError(e)
        return True

    def shipstation_get_tracking_link(self, pickings):
        res = ""
        for picking in pickings:
            if picking.shipstation_carrier_code:
                shipstation_carrier_id = self.env['shipstation.delivery.carrier'].search([('code','=',picking.shipstation_carrier_code)],limit=1)
                link = "%s" % (
                        shipstation_carrier_id.provider_tracking_link)
            else:
                shipstation_carrier_id = self.shipstation_carrier_id
                link = "%s" % (
                        picking.carrier_id and picking.carrier_id.shipstation_carrier_id and picking.carrier_id and picking.carrier_id.shipstation_carrier_id.provider_tracking_link)
            if not link:
                raise ValidationError("Provider Link Is not available")
            if len(pickings.carrier_tracking_ref.split(',')) > 1:
                if shipstation_carrier_id and shipstation_carrier_id.code in ["ups", "UPS", "ups_walleted",
                                                                                        "UPS_WALLETED"]:
                    res = '%s %s' % (link, pickings.carrier_tracking_ref.replace(",", "%20"))
                elif shipstation_carrier_id and shipstation_carrier_id.code in ["stamps_com", "STAMPS_COM"]:
                    res = '%s %s' % (link, pickings.carrier_tracking_ref.replace(",", "%2C"))
                else:
                    res = '%s %s' % (link, pickings.carrier_tracking_ref.replace(",", "&"))
            else:
                res = '%s %s' % (link, pickings.carrier_tracking_ref)

        return res
