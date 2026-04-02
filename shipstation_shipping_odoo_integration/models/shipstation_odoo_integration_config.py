import base64
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from requests import request


class ShipstationOdooIntegationConfig(models.Model):
    _name = "shipstation.odoo.configuration.vts"
    _description = 'Shipstation Configuration'

    api_key = fields.Char(string='API Key', help='Use Your Shipstation API Key.')
    api_secret = fields.Char(string='API Secret', help='Use Your Shipstation Password as API Secret.')
    api_url = fields.Char(string='URL', default="https://ssapi.shipstation.com")
    name = fields.Char(string='Name')
    message = fields.Char(string='Message')

    # V2 API fields
    use_v2_api = fields.Boolean(string='Use V2 API', default=False,
                                help='Enable ShipStation V2 API. V2 uses a single API key (no secret) and different endpoints.')
    api_key_v2 = fields.Char(string='V2 API Key',
                             help='Your ShipStation V2 API key. Generated separately from V1 credentials.')
    api_url_v2 = fields.Char(string='V2 URL', default="https://api.shipstation.com",
                             help='ShipStation V2 API base URL.')

    def create_shipstation_operation_details(self,operation_id,shipstation_response_message,fault_operaion=False):
        shipstation_operation_details = self.env['shipstation.operation.details']
        shipstation_operation_details.create({
                    'operation_id': operation_id and operation_id.id,
                    'shipstation_response_message': shipstation_response_message,
                    'fault_operaion': fault_operaion,
                    'shipstation_operation': 'warehouse'
                })

    def action_get_shipstation_stores(self):
        action = self.env.ref('shipstation_shipping_odoo_integration.actionid_shipstation_store_vts').read()[0]
        return action

    def action_action_get_shipstation_providers(self):
        action = self.env.ref('shipstation_shipping_odoo_integration.actionid_shipstation_delivery_carrier_vts').read()[
            0]
        return action

    def action_get_shipstation_services(self):
        action = \
        self.env.ref('shipstation_shipping_odoo_integration.actionid_shipstation_delivery_carrier_service_vts').read()[
            0]
        return action

    def action_get_shipstation_packages(self):
        action = self.env.ref('shipstation_shipping_odoo_integration.actionid_shipstation_delivery_package_vts').read()[
            0]
        return action

    def api_calling_function(self, url):
        data = "%s:%s" % (self.api_key, self.api_secret)
        encode_data = base64.b64encode(data.encode("utf-8"))
        authrization_data = "Basic %s" % (encode_data.decode("utf-8"))
        headers = {"Authorization": "%s" % authrization_data}
        try:
            response_data = request(method='GET', url=url, headers=headers)
            return response_data
        except Exception as e:
            raise ValidationError(e)

    def api_calling_function_v2(self, url, method='GET', body=None):
        """Make a V2 API call using the API-Key header."""
        if not self.api_key_v2:
            raise ValidationError(_("V2 API Key is not configured."))
        headers = {
            "API-Key": self.api_key_v2,
            "Content-Type": "application/json",
        }
        try:
            import json
            data = json.dumps(body) if body else None
            response_data = request(method=method, url=url, data=data, headers=headers)
            return response_data
        except Exception as e:
            raise ValidationError(e)

    def making_shipstation_url(self, api_name):
        if self.api_url:
            url = self.api_url + api_name
            return url
        else:
            raise ValidationError(_("URL is not appropriate."))

    def making_shipstation_url_v2(self, api_name):
        """Build a V2 API URL."""
        url = self.api_url_v2 or "https://api.shipstation.com"
        return url + api_name

    def delivery_carrier_package_process(self):
        carrier_name = self.env['shipstation.delivery.carrier'].search([])
        for carrier in carrier_name:
            url = self.making_shipstation_url("/carriers/listpackages?carrierCode=%s" % (carrier.code))
            response = self.api_calling_function(url)
            if response.status_code != 200:
                error = "Error Code : %s - %s" % (response.status_code, response.reason)
            shipstation_operation_detail = self.env['shipstation.operation.detail']
            shipstation_operation_details = self.env['shipstation.operation.details']
            shipstation_delivery_carrier_package = self.env['shipstation.delivery.package']
            operation = False
            if not operation:
                operation_id = shipstation_operation_detail.create({
                    'shipstation_operation': 'carrier_package', 'shipstation_operation_type': 'import',
                    'message': 'Delivery Carrier Package Imported',
                })
            try:
                responses = response.json()
                for response in responses:
                    shipstation_delivery_carrier_package = shipstation_delivery_carrier_package.search(
                        [('package_code', '=',response.get('code')), ('delivery_carrier_id', '=', carrier.id),('shipstation_configuration_id', '=', self.id)])
                    if not shipstation_delivery_carrier_package:
                        carrier_id = self.env['shipstation.delivery.carrier'].search(
                            [('code', '=', response.get('carrierCode', False)),('shipstation_configuration_id', '=', self.id)])
                        shipstation_delivery_carrier_package.create({'name': response.get('name', False),
                                                                     'package_code': response.get('code', False),
                                                                     'shipstation_configuration_id': self.id,
                                                                     'service_nature': 'domestic' if response.get(
                                                                         'domestic', False) else 'international',
                                                                     'delivery_carrier_id': carrier_id.id,
                                                                     'supported_domestic':True if response.get('domestic') else False,
                                                                     'supported_international':True if response.get('international') else False
                                                                     })
                        shipstation_operation_details.create(
                            {'operation_id': operation_id.id,
                             'shipstation_response_message': "%s Delivery Carrier Service Created" % (
                                 response.get('name')), 'fault_operaion': False,
                             'shipstation_operation': 'carrier_package'})
                    else:
                        shipstation_delivery_carrier_package.write({'shipstation_configuration_id':self.id})
                        shipstation_operation_details.create(
                            {'operation_id': operation_id.id,
                             'shipstation_response_message': "%s Delivery Carrier Service already exist" % (
                                 response.get('name')),
                             'fault_operaion': True,
                             'shipstation_operation': 'carrier_package'})
            except Exception as e:
                shipstation_operation_details.create(
                    {'operation_id': operation_id.id, 'shipstation_response_message': e, 'fault_operaion': True,
                     'shipstation_operation': 'carrier_service'})

    def delivery_carrier_service_process(self):
        carrier_name = self.env['shipstation.delivery.carrier'].search([('shipstation_configuration_id', '=', self.id)])
        shipstation_delivery_carrier_service = self.env['shipstation.delivery.carrier.service']
        shipstation_operation_detail = self.env['shipstation.operation.detail']
        shipstation_operation_details = self.env['shipstation.operation.details']
        for carrier in carrier_name:
            operation = False
            if not operation:
                operation_id = shipstation_operation_detail.create({
                    'shipstation_operation': 'carrier_service', 'shipstation_operation_type': 'import',
                    'message': 'Delivery Carrier Service Imported',
                })
            url = self.making_shipstation_url("/carriers/listservices?carrierCode=%s" % (carrier.code))
            response = self.api_calling_function(url)
            if response.status_code != 200:
                error = "Error Code : %s - %s" % (response.status_code, response.reason)
                responses = response.json()
                shipstation_operation_details.create(
                    {'operation_id': operation_id.id,
                     'shipstation_response_message':responses.get('message'), 'fault_operaion': True,
                     'shipstation_operation': 'carrier_service'})
                continue
            try:
                responses = response.json()
                for response in responses:
                    shipstation_delivery_carrier_service = shipstation_delivery_carrier_service.search(
                        [('name', '=', response.get('name', False)),('shipstation_configuration_id', '=', self.id)])
                    if not shipstation_delivery_carrier_service:
                        carrier_id = self.env['shipstation.delivery.carrier'].search(
                            [('code', '=', response.get('carrierCode', False)),('shipstation_configuration_id', '=', self.id)])
                        shipstation_delivery_carrier_service.create({'name': response.get('name', False),
                                                                     'service_code': response.get('code', False),
                                                                     'shipstation_configuration_id': self.id,
                                                                     'service_nature': 'domestic' if response.get(
                                                                         'domestic', False) else 'international',
                                                                     'delivery_carrier_id': carrier_id.id,
                                                                     'supported_domestic': True if response.get('domestic') else False,
                                                                     'supported_international': True if response.get('international') else False
                                                                     })
                        shipstation_operation_details.create(
                            {'operation_id': operation_id.id,
                             'shipstation_response_message': "%s Delivery Carrier Service Created" % (
                                 response.get('name')), 'fault_operaion': False,
                             'shipstation_operation': 'carrier_service'})
                    else:
                        shipstation_delivery_carrier_service.write({'shipstation_configuration_id':self.id})
                        shipstation_operation_details.create(
                            {'operation_id': operation_id.id,
                             'shipstation_response_message': "%s Delivery Carrier Service already exist" % (
                                 response.get('name')),
                             'fault_operaion': True,
                             'shipstation_operation': 'carrier_service'})
            except Exception as e:
                shipstation_operation_details.create(
                    {'operation_id': operation_id.id, 'shipstation_response_message': e, 'fault_operaion': True,
                     'shipstation_operation': 'carrier_service'})

    def carrier_create_process(self):
        url = self.making_shipstation_url("/carriers")
        response = self.api_calling_function(url)
        if response.status_code != 200:
            error = "Error Code : %s - %s" % (response.status_code, response.reason)
        shipstation_operation_detail = self.env['shipstation.operation.detail']
        shipstation_operation_details = self.env['shipstation.operation.details']
        shipstation_delivery_carrier = self.env['shipstation.delivery.carrier']
        operation = False
        if not operation:
            operation_id = shipstation_operation_detail.create(
                {'shipstation_operation': 'delivery_carrier', 'shipstation_operation_type': 'import',
                 'message': 'Delivery Carrier Imported',
                 })
        try:
            responses = response.json()
            for response in responses:
                delivery_carrier = shipstation_delivery_carrier.search([('code', '=', response.get('code', False)),('shipstation_configuration_id', '=', self.id)])
                if not delivery_carrier:
                    shipstation_delivery_carrier.create({'name': response.get('name', False),
                                                         'shipstation_configuration_id': self.id,
                                                         'code': response.get('code', False),
                                                         'account_number': response.get('accountNumber', False),
                                                         'shipping_provider_id': response.get('shippingProviderId',
                                                                                              False)
                                                         })
                    shipstation_operation_details.create(
                        {'operation_id': operation_id.id,
                         'shipstation_response_message': "%s Delivery Carrier Created" % (response.get('name')),
                         'fault_operaion': False,
                         'shipstation_operation': 'delivery_carrier'})
                else:
                    shipstation_delivery_carrier.write({'shipstation_configuration_id': self.id})
                    shipstation_operation_details.create(
                        {'operation_id': operation_id.id,
                         'shipstation_response_message': "%s Delivery Carrier already exist" % (response.get('name')),
                         'fault_operaion': True,
                         'shipstation_operation': 'delivery_carrier'})
        except Exception as e:
            shipstation_operation_details.create(
                {'operation_id': operation_id.id, 'shipstation_response_message': e, 'fault_operaion': True,
                 'shipstation_operation': 'delivery_carrier'})

    def store_create_process(self):
        url = self.making_shipstation_url("/stores?stores?showInactive=false")
        response = self.api_calling_function(url)
        if response.status_code != 200:
            raise ValidationError("Error Code : %s - %s" % (response.status_code, response.reason))
        shipstation_operation_detail = self.env['shipstation.operation.detail']
        shipstation_operation_details = self.env['shipstation.operation.details']
        shipstation_store = self.env['shipstation.store.vts']
        operation = False
        if not operation:
            operation_id = shipstation_operation_detail.create(
                {'shipstation_operation': 'store', 'shipstation_operation_type': 'import', 'message': 'Store Imported',
                 })
        try:
            responses = response.json()
            for response in responses:
                store = shipstation_store.search([('store_id', '=', response.get('storeId', False)),('shipstation_configuration_id', '=', self.id)])
                if not store:
                    shipstation_store.create({'store_id': response.get('storeId', False),
                                              'store_name': response.get('storeName', False),
                                              'marketplace_id': response.get('marketplaceId', False),
                                              'marketplace_name': response.get('marketplaceName', False),
                                              'shipstation_configuration_id': self.id,
                                              'acc_number': response.get('accountName', False)})
                    shipstation_operation_details.create(
                        {'operation_id': operation_id.id,
                         'shipstation_response_message': "%s Store Created" % (response.get('storeName')),
                         'fault_operaion': False,
                         'shipstation_operation': 'store'})
                else:
                    shipstation_store.write({'shipstation_configuration_id':self.id})
                    shipstation_operation_details.create(
                        {'operation_id': operation_id.id,
                         'shipstation_response_message': "%s Store already exist" % (response.get('storeName')),
                         'fault_operaion': True,
                         'shipstation_operation': 'store'})
        except Exception as e:
            shipstation_operation_details.create(
                {'operation_id': operation_id.id, 'shipstation_response_message': e, 'fault_operaion': True,
                 'shipstation_operation': 'store'})

    def import_warehouse_from_shipstation(self):
        self.ensure_one()
        vals = {}
        shipstation_operation_detail = self.env['shipstation.operation.detail']
        shipstation_operation_details = self.env['shipstation.operation.details']
        operation_id = shipstation_operation_detail.create({
            'shipstation_operation': 'warehouse', 'shipstation_operation_type': 'import',
            'message': 'Warehouse Import Process',
        })
        try:
            url = self.making_shipstation_url('/warehouses')
            response_data = self.api_calling_function(url)
            if response_data.status_code != 200:
                raise ValidationError("Error Code : %s - %s" % (response_data.status_code, response_data.reason))
            if response_data.status_code == 200:
                responses = response_data.json()
                for warehouse in responses:
                    sh_warehouse = self.env['shipstation.warehouse.detail'].search(
                        [('warehouse_id', '=', warehouse.get('warehouseId')),('shipstation_configuration_id', '=', self.id)])
                    if not sh_warehouse:
                        warehouse = self.env['shipstation.warehouse.detail'].create(
                            {'name': warehouse.get('warehouseName'), 'shipstation_configuration_id': self.id, 'warehouse_id': warehouse.get('warehouseId')})
                        if warehouse:
                            response_msg = "Warehouse Created Updated : {0}".format(warehouse.name)
                            self.create_shipstation_operation_details(operation_id, response_msg, False)
                    else:
                        sh_warehouse.write({'shipstation_configuration_id':self.id})
        except Exception as e:
            response_msg = "%s Warehouse Not Imported %s" % (self.name, e)
            self.create_shipstation_operation_details(operation_id, response_msg, True)

    # Known aliases between V1 and V2 carrier codes.
    # V2 uses canonical short codes; V1 may use branded/suffixed variants.
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

    def _v2_carrier_code_variants(self, code):
        """Generate all possible code variants for matching.
        Includes suffix permutations AND known aliases."""
        variants = {code}
        # Add common suffixes / strip them
        for suffix in ['_walleted', '_ltl_walleted']:
            variants.add(code + suffix)
            if code.endswith(suffix):
                variants.add(code[:-len(suffix)])
        # Add known aliases
        alias = self._V1_V2_CODE_ALIASES.get(code)
        if alias:
            variants.add(alias)
            # Also try suffix variants of the alias
            for suffix in ['_walleted', '_ltl_walleted']:
                variants.add(alias + suffix)
                if alias.endswith(suffix):
                    variants.add(alias[:-len(suffix)])
        return list(variants)

    def import_v2_carriers(self):
        """Fetch carriers from V2 API and update v2_carrier_id on existing carrier records.
        Propagates v2_carrier_id to ALL variant V1 carriers (not just first match)."""
        self.ensure_one()
        if not self.use_v2_api or not self.api_key_v2:
            raise ValidationError(_("V2 API is not enabled or V2 API Key is missing."))
        url = self.making_shipstation_url_v2('/v2/carriers')
        response = self.api_calling_function_v2(url, method='GET')
        if response.status_code != 200:
            raise ValidationError("V2 Carrier Import Error: %s - %s" % (response.status_code, response.text))
        carriers_data = response.json()
        carrier_list = carriers_data.get('carriers', carriers_data) if isinstance(carriers_data, dict) else carriers_data
        shipstation_carrier_obj = self.env['shipstation.delivery.carrier']
        all_v1_carriers = shipstation_carrier_obj.search([
            ('shipstation_configuration_id', '=', self.id),
        ])
        logging.info("=== V2 CARRIER IMPORT START === V1 carriers in DB: %s",
                      [(c.code, c.name, c.v2_carrier_id) for c in all_v1_carriers])
        updated = 0
        unmatched = []
        for carrier_data in carrier_list:
            v2_carrier_id = carrier_data.get('carrier_id', '')
            carrier_code = carrier_data.get('carrier_code', '')
            nickname = carrier_data.get('nickname', carrier_data.get('friendly_name', ''))
            account_number = carrier_data.get('account_number', '')
            logging.info("V2 carrier: code=%s, id=%s, nickname=%s, account=%s",
                         carrier_code, v2_carrier_id, nickname, account_number)
            if not carrier_code:
                continue

            # Collect ALL V1 carriers that should receive this v2_carrier_id
            all_code_variants = self._v2_carrier_code_variants(carrier_code)
            logging.info("V2 code '%s' → checking V1 variants: %s", carrier_code, all_code_variants)

            matched_carriers = self.env['shipstation.delivery.carrier']

            # Strategy 1: Match by any code variant
            for variant in all_code_variants:
                found = all_v1_carriers.filtered(lambda c, v=variant: c.code == v)
                if found:
                    matched_carriers |= found
                    logging.info("  Variant '%s' matched V1 carriers: %s", variant,
                                 [(c.code, c.name) for c in found])

            # Strategy 2: Match by account number
            if account_number:
                found = all_v1_carriers.filtered(
                    lambda c: c.account_number and c.account_number == account_number)
                if found:
                    matched_carriers |= found
                    logging.info("  Account number '%s' matched V1 carriers: %s", account_number,
                                 [(c.code, c.name) for c in found])

            # Strategy 3: Match by shipping_provider_id
            sp_id = carrier_data.get('shipping_provider_id', '')
            if sp_id:
                found = all_v1_carriers.filtered(
                    lambda c, sid=str(sp_id): c.shipping_provider_id and c.shipping_provider_id == sid)
                if found:
                    matched_carriers |= found
                    logging.info("  Provider ID '%s' matched V1 carriers: %s", sp_id,
                                 [(c.code, c.name) for c in found])

            if matched_carriers:
                for mc in matched_carriers:
                    mc.write({'v2_carrier_id': v2_carrier_id})
                    logging.info("  SET v2_carrier_id=%s on V1 carrier: code=%s, name=%s",
                                 v2_carrier_id, mc.code, mc.name)
                updated += len(matched_carriers)
            else:
                unmatched.append("%s (%s)" % (carrier_code, v2_carrier_id))
                logging.warning("V2 carrier NOT matched to any V1 carrier: code=%s, id=%s, nickname=%s",
                                carrier_code, v2_carrier_id, nickname)

        if unmatched:
            logging.warning("V2 carriers with no V1 match: %s", ', '.join(unmatched))
        logging.info("=== V2 CARRIER IMPORT DONE === updated %d V1 carrier records, %d unmatched",
                      updated, len(unmatched))

    def import_store_from_shipstation(self):
        self.store_create_process()
        self.carrier_create_process()
        self.delivery_carrier_service_process()
        self.delivery_carrier_package_process()
        self.import_warehouse_from_shipstation()
        # Also sync V2 carrier IDs if V2 is enabled
        if self.use_v2_api and self.api_key_v2:
            try:
                self.import_v2_carriers()
            except Exception as e:
                logging.warning("V2 carrier sync failed (non-blocking): %s", e)
        self.message = "Shipstation Import Process Completed Sucessfully.."
        self._cr.commit()
        return {
            'effect': {
                'fadeout': 'slow',
                'message': 'Import Shipstation Data Successfully!',
                'img_url': '/web/static/img/smile.svg',
                'type': 'rainbow_man',
            }
        }
