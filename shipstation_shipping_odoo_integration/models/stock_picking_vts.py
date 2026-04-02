import os
import base64
import binascii
import logging
import json
from requests import request
from PyPDF2 import PdfFileMerger
from odoo.exceptions import ValidationError
from odoo import fields, models, api, _
from odoo.tools import pdf

class StockPicking(models.Model):
    _inherit = "stock.picking"

    @api.model
    def _shipstation_default_delivery_carrier(self):
        """Return default `delivery.carrier` for ShipStation, if available."""
        Carrier = self.env["delivery.carrier"].sudo()
        domain = [("delivery_type", "=", "shipstation"), ("active", "=", True)]
        # Prefer company-specific carrier when possible
        company = self.env.company
        if "company_id" in Carrier._fields and company:
            domain = ["|", ("company_id", "=", False), ("company_id", "=", company.id)] + domain

        carriers = Carrier.search(domain)
        if not carriers:
            return Carrier
        if len(carriers) == 1:
            return carriers

        preferred = carriers.filtered(lambda c: (c.name or "").strip().lower() in {"ship station", "shipstation"})
        return preferred[:1] or carriers[:1]

    @api.model
    def _shipstation_default_provider_carrier(self, shipstation_config=None):
        """Return the default ShipStation provider carrier (stamps_com), if present."""
        SSCarrier = self.env["shipstation.delivery.carrier"].sudo()
        domain = [("code", "=", "stamps_com")]
        if shipstation_config:
            domain.append(("shipstation_configuration_id", "=", shipstation_config.id))
        carrier = SSCarrier.search(domain, limit=1)
        if carrier:
            return carrier
        # Fallback: try USPS (some accounts alias stamps_com/usps)
        domain = [("code", "in", ["usps", "stamps_com"])]
        if shipstation_config:
            domain.append(("shipstation_configuration_id", "=", shipstation_config.id))
        return SSCarrier.search(domain, limit=1)

    @api.model
    def _shipstation_default_package(self, shipstation_provider_carrier=None, shipstation_config=None):
        """Return the default ShipStation package (package), if present."""
        SSPackage = self.env["shipstation.delivery.package"].sudo()
        domain = [("package_code", "=", "package")]
        if shipstation_provider_carrier:
            domain.append(("delivery_carrier_id", "=", shipstation_provider_carrier.id))
        if shipstation_config:
            domain.append(("shipstation_configuration_id", "=", shipstation_config.id))
        package = SSPackage.search(domain, limit=1)
        if package:
            return package
        # Fallback by name (case-insensitive)
        domain = [("name", "=ilike", "Package")]
        if shipstation_provider_carrier:
            domain.append(("delivery_carrier_id", "=", shipstation_provider_carrier.id))
        if shipstation_config:
            domain.append(("shipstation_configuration_id", "=", shipstation_config.id))
        return SSPackage.search(domain, limit=1)

    shipstation_order_id = fields.Char(string="Shipstation Order ID", copy=False)
    shipstation_order_key = fields.Char(string="Shipstation Order Key", copy=False)
    shipstation_shipment_id = fields.Char(string="Shipstation Shipment ID", copy=False)
    delivery_package_id = fields.Many2one(
        'shipstation.delivery.package',
        string='ShipStation Package',
        domain="[('delivery_carrier_id', '=', shipstation_carrier_id)]"
    )
    shipstation_delivery_carrier_id = fields.Many2one('shipstation.delivery.carrier', string='Shipstation Carrier Code')
    shipstation_carrier_id = fields.Many2one(
        'shipstation.delivery.carrier',
        string='ShipStation Carrier',
        help='Carrier to use when fetching ShipStation rates.'
    )

    height = fields.Float(related="delivery_package_id.height", readonly=False)
    width = fields.Float(related="delivery_package_id.width", readonly=False)
    length = fields.Float(related="delivery_package_id.length", readonly=False)
    shipstation_shipping_charge_ids = fields.One2many(
        'shipstation.shipping.charge',
        'picking_id',
        string='ShipStation Shipping Charges'
    )
    shipstation_shipping_charge_id = fields.Many2one("shipstation.shipping.charge", string="Shipstation Service",
                                                     help="This Method Is Use Full For Generating The Label",
                                                     copy=False)

    is_order_imported_in_shipstation = fields.Boolean("Imported Shipstation Shipment", copy=False, default=False,
                                                      help="If Checked, This order is Imported From shipstation.")
    shipstation_service_code = fields.Char(string="Shipstation Shipment Wise Service Code", copy=False)
    shipstation_weight = fields.Float(string='Shipstation Order Weight')
    shipstation_unit_of_measure = fields.Char(string='Shipstation Units')
    shipstation_carrier_code = fields.Char(string='Carrier Code')
    shipstation_sale_order_number = fields.Char(string="Shipstation Order Number", copy=False)
    shipstation_batch_number = fields.Char(string='Shipstation Batch')
    shipment_cost = fields.Float(string='Shipment Cost')
    shipstation_configuration_id = fields.Many2one('shipstation.odoo.configuration.vts', string='Shipstation Configuration')
    shipstation_insurance_provider = fields.Selection([('shipsurance', 'shipsurance'), ('carrier', 'carrier'), ('provider', 'provider'), ('xcover', 'xcover'), ('parcelguard', 'parcelguard')], string='Insurance Provider', help='The provider option is used to indicate that a shipment was insured by a third party other than Shipsurance, XCover, ParcelGuard or the carrier. Billing for provider insurance is handled outside of ShipStation, and will not affect the cost of processing the label.')
    insureshipment = fields.Boolean(string='insureShipment', copy=False)
    insuredvalue = fields.Integer(string='Insurance Amount', copy=False)
    show_shipstation_carrier = fields.Boolean(string='Show Shipstation Carrier', copy=False, compute='_compute_show_shipstation_carrier')
    
    @api.depends('carrier_id')
    def _compute_show_shipstation_carrier(self):
        for picking in self:
            picking.show_shipstation_carrier = picking.carrier_id and picking.carrier_id.delivery_type == 'shipstation'

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        # Only default for outgoing deliveries when creating a new picking.
        picking_type_id = self.env.context.get("default_picking_type_id")
        if picking_type_id:
            picking_type = self.env["stock.picking.type"].browse(picking_type_id)
            if picking_type and picking_type.code != "outgoing":
                return res

        if "carrier_id" in fields_list and not res.get("carrier_id"):
            carrier = self._shipstation_default_delivery_carrier()
            if carrier:
                res["carrier_id"] = carrier.id

        # Default ShipStation provider + package when carrier is ShipStation.
        carrier_id = res.get("carrier_id")
        if carrier_id and any(f in fields_list for f in ("shipstation_carrier_id", "shipstation_delivery_carrier_id", "delivery_package_id")):
            carrier = self.env["delivery.carrier"].browse(carrier_id)
            if carrier and carrier.delivery_type == "shipstation":
                config = carrier.shipstation_configuration_id
                ss_provider = self._shipstation_default_provider_carrier(shipstation_config=config)
                if ss_provider and "shipstation_carrier_id" in fields_list and not res.get("shipstation_carrier_id"):
                    res["shipstation_carrier_id"] = ss_provider.id
                if ss_provider and "shipstation_delivery_carrier_id" in fields_list and not res.get("shipstation_delivery_carrier_id"):
                    res["shipstation_delivery_carrier_id"] = ss_provider.id

                ss_package = self._shipstation_default_package(
                    shipstation_provider_carrier=ss_provider, shipstation_config=config
                )
                if ss_package and "delivery_package_id" in fields_list and not res.get("delivery_package_id"):
                    res["delivery_package_id"] = ss_package.id

        return res

    @api.onchange("carrier_id")
    def _onchange_carrier_id_shipstation_defaults(self):
        for picking in self:
            if not picking.carrier_id or picking.carrier_id.delivery_type != "shipstation":
                continue
            config = picking.carrier_id.shipstation_configuration_id
            if not picking.shipstation_carrier_id:
                picking.shipstation_carrier_id = picking._shipstation_default_provider_carrier(shipstation_config=config)
            if not picking.shipstation_delivery_carrier_id:
                picking.shipstation_delivery_carrier_id = picking.shipstation_carrier_id
            if not picking.delivery_package_id:
                picking.delivery_package_id = picking._shipstation_default_package(
                    shipstation_provider_carrier=picking.shipstation_carrier_id, shipstation_config=config
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for picking in records:
            if picking.picking_type_id and picking.picking_type_id.code != "outgoing":
                continue
            if not picking.carrier_id:
                carrier = picking._shipstation_default_delivery_carrier()
                if carrier:
                    picking.carrier_id = carrier
            if picking.carrier_id and picking.carrier_id.delivery_type == "shipstation":
                config = picking.carrier_id.shipstation_configuration_id
                if not picking.shipstation_carrier_id:
                    picking.shipstation_carrier_id = picking._shipstation_default_provider_carrier(shipstation_config=config)
                if not picking.shipstation_delivery_carrier_id:
                    picking.shipstation_delivery_carrier_id = picking.shipstation_carrier_id
                if not picking.delivery_package_id:
                    picking.delivery_package_id = picking._shipstation_default_package(
                        shipstation_provider_carrier=picking.shipstation_carrier_id, shipstation_config=config
                    )
        return records

    def _put_in_pack(self, move_line_ids):
        """Ensure packages created from the standard Put in Pack flow inherit ShipStation defaults."""
        package = super()._put_in_pack(move_line_ids)
        if not package or not self.carrier_id or self.carrier_id.delivery_type != "shipstation":
            return package

        vals = {}
        if hasattr(package, "is_generate_label_in_shipstation") and not package.is_generate_label_in_shipstation:
            vals["is_generate_label_in_shipstation"] = True
        if hasattr(package, "carrier_id") and not package.carrier_id:
            vals["carrier_id"] = self.carrier_id.id
        if hasattr(package, "shipstation_delivery_package_id") and not package.shipstation_delivery_package_id and self.delivery_package_id:
            vals["shipstation_delivery_package_id"] = self.delivery_package_id.id

        if vals:
            logging.info("ShipStation defaults applied to package %s from picking %s: %s", package.id, self.name, vals)
            package.write(vals)
        return package
    def button_check_shipstation_rates(self):
        self.ensure_one()

        if not self.carrier_id:
            raise ValidationError("Please select a delivery carrier.")

        if self.carrier_id.delivery_type == 'shipstation':
            self._validate_shipstation_label_requirements()

        wizard_vals = {'picking_id': self.id}
        package_id = self.env.context.get("shipstation_package_id")
        if package_id:
            wizard_vals["package_id"] = package_id

        wizard = self.env['shipstation.carrier.selection.wizard'].create(wizard_vals)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'carrier_selection_wizard',
            'params': {
                'wizard_id': wizard.id,
                'picking_id': self.id,
                'package_id': package_id,
            }
        }

    def action_open_put_in_pack_wizard(self):
        """Open the ShipStation Put in Pack OWL wizard."""
        self.ensure_one()
        wizard = self.env['shipstation.put.in.pack.wizard'].create({
            'picking_id': self.id,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'shipstation_put_in_pack_wizard',
            'params': {
                'wizard_id': wizard.id,
                'picking_id': self.id,
            },
        }

    def action_open_generate_all_labels(self):
        """Open the Generate All Labels wizard for this picking."""
        self.ensure_one()
        wizard = self.env['shipstation.generate.all.labels.wizard'].create({
            'picking_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generate All Labels'),
            'res_model': 'shipstation.generate.all.labels.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_download_latest_label(self):
        """Download the most recent shipping label for this picking."""
        self.ensure_one()
        att = self.env['ir.attachment'].search([
            ('res_model', '=', 'stock.picking'),
            ('res_id', '=', self.id),
            ('mimetype', '=', 'application/pdf'),
        ], order='id desc', limit=1)
        if not att:
            raise ValidationError(_("No label found for this delivery order."))
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download_document?model=ir.attachment&field=datas&id=%s&filename=%s.pdf' % (
                att.id, (self.name or 'label').replace('/', '_')),
            'target': 'self',
        }

    def check_shipstation_validation_requirements(self):
        """Check that the picking meets minimum requirements for packing.
        Called from the Put in Pack OWL wizard before creating packages."""
        self.ensure_one()
        if not self.partner_id:
            return {'can_validate': False, 'message': 'No delivery address set on this transfer.'}
        return {'can_validate': True}

    def _get_related_sale_order(self):
        """Return the related sale.order, if any."""
        # Direct link (enterprise shipping or custom modules)
        if hasattr(self, "sale_id") and self.sale_id:
            return self.sale_id

        # Fallback: get from stock moves
        so = self.move_lines.mapped("sale_line_id.order_id")
        if so:
            return so[0]

        # Fallback: parse origin SOXXXX
        if self.origin:
            so = self.env["sale.order"].search([("name", "=", self.origin)], limit=1)
            if so:
                return so

        return False

    def button_validate(self):
        for picking in self:
            missing = []
            logging.info(" Custom Code:Validating Picking for Shipstation Requirements: %s" % (picking.name))
            logging.info(" Custom Code:Picking Type Code: %s" % (picking.picking_type_code))
            logging.info(" Custom Code:Carrier ID: %s" % (picking.carrier_id))
            logging.info(" Custom Code:Delivery Package ID: %s" % (picking.delivery_package_id))
            # Only enforce for outgoing deliveries; skip receipts/internal if you want
            carrier = picking.carrier_id
            
            if carrier and carrier.delivery_type == 'shipstation' and picking.picking_type_code == 'outgoing':
                missing = []
                if not picking.carrier_id:
                    missing.append(_("Carrier"))
                if not picking.delivery_package_id:
                    missing.append(_("Delivery Package"))
                if missing:
                    raise ValidationError(_(
                        "Cannot validate this transfer.\n"
                        "Please set the following: %s"
                    ) % ", ".join(missing))
            partner = picking.partner_id
            if partner and picking.picking_type_code == 'outgoing':
                if not partner.street:
                    missing.append(_("Customer Street Address"))
                if not partner.city:
                    missing.append(_("Customer City"))
                if not partner.zip:
                    missing.append(_("Customer ZIP"))

            if missing:
                raise ValidationError(_(
                    "Cannot validate this transfer.\n"
                    "Please set the following: %s"
                ) % ", ".join(missing))

        return super().button_validate()

    def _get_shipstation_dimension_value(self, field_name):
        self.ensure_one()
        value = getattr(self, field_name, False)
        if self.delivery_package_id:
            return value if value is not False and value is not None else 0.0
        if value and value > 0:
            return value
        carrier_package = self.carrier_id and self.carrier_id.delivery_package_id
        if carrier_package:
            carrier_value = getattr(carrier_package, field_name, False)
            if carrier_value and carrier_value > 0:
                return carrier_value
        return 0.0

    def _get_shipstation_dimensions(self):
        self.ensure_one()
        return {
            'length': self._get_shipstation_dimension_value('length'),
            'width': self._get_shipstation_dimension_value('width'),
            'height': self._get_shipstation_dimension_value('height'),
        }

    def _get_shipstation_address_lines(self):
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return []
        lines = []
        if partner.name:
            lines.append(partner.name)
        if partner.street:
            lines.append(partner.street)
        if partner.street2:
            lines.append(partner.street2)
        city_parts = []
        if partner.city:
            city_parts.append(partner.city)
        if partner.state_id:
            city_parts.append(partner.state_id.name)
        city_state = ", ".join(city_parts) if city_parts else ""
        if partner.zip:
            city_state = f"{city_state} {partner.zip}".strip() if city_state else partner.zip
        if city_state:
            lines.append(city_state)
        if partner.country_id:
            lines.append(partner.country_id.name)
        return lines

    def get_shipstation_label_summary(self):
        self.ensure_one()
        ctx_package_id = self.env.context.get("shipstation_package_id")
        package = self.env["stock.quant.package"].browse(ctx_package_id) if ctx_package_id else self.env["stock.quant.package"]

        dims = self._get_shipstation_dimensions()
        weight_value = self.shipping_weight or 0.0
        source = "picking"

        if package and package.exists():
            source = "package"
            dims = {
                "length": package.length or dims.get("length", 0.0) or 0.0,
                "width": package.width or dims.get("width", 0.0) or 0.0,
                "height": package.height or dims.get("height", 0.0) or 0.0,
            }
            weight_value = package.shipping_weight or package.weight or weight_value or 0.0

        length = dims.get('length', 0.0) or 0.0
        width = dims.get('width', 0.0) or 0.0
        height = dims.get('height', 0.0) or 0.0
        weight_uom = self.env['product.template']._get_weight_uom_name_from_ir_config_parameter()
        dimension_display = f"{length:.2f} x {width:.2f} x {height:.2f}"
        weight_display = f"{weight_value:.2f} {weight_uom}"
        return {
            'source': source,
            'package_id': package.id if source == "package" else False,
            'dimension_display': dimension_display,
            'dimensions': dims,
            'weight_value': weight_value,
            'weight_display': weight_display,
            'weight_uom': weight_uom,
            'address_lines': self._get_shipstation_address_lines(),
        }

    def _validate_shipstation_label_requirements(self):
        self.ensure_one()
        errors = []

        partner = self.partner_id
        if not partner:
            errors.append(_("Delivery contact is missing."))
        else:
            if not partner.street:
                errors.append(_("Receiver address is missing the street."))
            if not partner.city:
                errors.append(_("Receiver address is missing the city."))
            if not partner.state_id:
                errors.append(_("Receiver address is missing the state."))
            if not partner.zip:
                errors.append(_("Receiver address is missing the ZIP code."))
            if not partner.country_id:
                errors.append(_("Receiver address is missing the country."))

        dims = self._get_shipstation_dimensions()
        for key, label in [('length', _("Length")), ('width', _("Width")), ('height', _("Height"))]:
            if dims.get(key, 0.0) <= 0:
                errors.append(_("%s must be greater than zero.") % label)

        if self.shipping_weight <= 0:
            errors.append(_("Shipping weight must be greater than zero."))

        if not any(move.product_uom_qty > 0 for move in self.move_ids):
            errors.append(_("At least one move needs a quantity greater than zero."))

        if errors:
            raise ValidationError("\n".join(errors))

    def update_order_in_shipstation(self):
        self.ensure_one()
        if not self.carrier_id:
            raise ValidationError("Please set proper delivery method")
        try:
            body = self.carrier_id and self.carrier_id.create_or_update_order(self)
            response_data = self.carrier_id and self.carrier_id.api_calling_function("/orders/createorder", body)
            if response_data.status_code == 200:
                responses = response_data.json()
                order_id = responses.get('orderId')
                order_key = responses.get('orderKey')
                if order_id:
                    self.shipstation_order_id = order_id
                    self.shipstation_order_key = order_key
            else:
                error_code = "%s" % (response_data.status_code)
                error_message = response_data.reason
                error_detail = {'error': error_code + " - " + error_message + " - "}
                if response_data.json():
                    error_detail = {'error': error_code + " - " + error_message + " - %s" % (response_data.json())}
                raise ValidationError(error_detail)
        except Exception as e:
            raise ValidationError(e)

    def ensure_shipstation_order(self):
        self.ensure_one()
        if not self.shipstation_order_id:
            self.update_order_in_shipstation()
        return True

    def _is_v2_enabled(self):
        """Check if V2 API is enabled on the carrier's configuration."""
        carrier = self.carrier_id
        if carrier and carrier.shipstation_configuration_id:
            config = carrier.shipstation_configuration_id
            return config.use_v2_api and config.api_key_v2
        return False

    def _process_v2_label_response(self, response_data):
        """Parse a V2 label response and return (shipment_id, label_bytes, tracking_number, cost).
        Returns None on failure so caller can fall back to V1."""
        if response_data.status_code != 200:
            return None
        responses = response_data.json()
        shipment_id = responses.get('shipment_id', '') or responses.get('label_id', '')
        tracking_number = responses.get('tracking_number', '')
        cost_obj = responses.get('shipment_cost', {})
        cost = cost_obj.get('amount', 0.0) if isinstance(cost_obj, dict) else 0.0

        # Try inline label data first
        label_data_b64 = responses.get('label_data')
        if label_data_b64:
            label_bytes = binascii.a2b_base64(str(label_data_b64))
            return (shipment_id, label_bytes, tracking_number, cost)

        # Try download URL (pdf preferred)
        label_download = responses.get('label_download', {})
        pdf_url = label_download.get('pdf') or label_download.get('href')
        if pdf_url:
            # Handle data: URIs (base64-encoded inline PDF)
            if pdf_url.startswith('data:'):
                try:
                    # Format: data:application/pdf;base64,<base64data>
                    header, b64_data = pdf_url.split(',', 1)
                    label_bytes = binascii.a2b_base64(b64_data)
                    logging.info("V2 label decoded from data: URI (%d bytes)", len(label_bytes))
                    return (shipment_id, label_bytes, tracking_number, cost)
                except Exception as e:
                    logging.warning("V2 label data: URI decode failed: %s", e)
            else:
                try:
                    from requests import get as http_get
                    dl_response = http_get(pdf_url, timeout=30)
                    if dl_response.status_code == 200:
                        return (shipment_id, dl_response.content, tracking_number, cost)
                except Exception as e:
                    logging.warning("V2 label PDF download failed: %s", e)

        return None

    def generate_label_from_shipstation(self):
        logging.info(" Custom Code:>>>>>>>>>>>>>>>>>> Generate Label")
        shipment_cost = 0.0
        self.ensure_one()
        if not self.carrier_id:
            raise ValidationError("Please set proper delivery method")
        self._validate_shipstation_label_requirements()

        if not self.shipstation_shipping_charge_id:
            raise ValidationError("Please select a shipping service first by checking rates and selecting a service.")

        use_v2 = self._is_v2_enabled()
        final_tracking_number = []
        label_datas = []
        file_name = self.name
        pdf_merger = PdfFileMerger()
        file_name = file_name.replace('/', '_')
        file_path = "/tmp/waves/"
        directory = os.path.dirname(file_path)
        try:
            os.stat(directory)
        except:
            os.system("mkdir %s" % (file_path))
        error_detail = ""
        if not self.shipping_weight and any(move.product_id.weight <= 0.0 for move in self.move_ids):
            raise ValidationError("Need to set Product Weight or Shipping Weight on the delivery order.")

        package_ids = self.move_line_ids.mapped('result_package_id')
        for package_id in package_ids:
            logging.info(" Custom Code:Inside Package : %s" % (package_id))
            try:
                if not package_id.is_generate_label_in_shipstation:
                    continue
                weight = package_id.shipping_weight
                carrier_id = package_id.carrier_id if package_id.carrier_id else self.carrier_id

                v2_success = False
                if use_v2:
                    try:
                        response_data = carrier_id.generate_label_from_shipstation_v2(
                            self, package_id, weight, shipstation_charge=self.shipstation_shipping_charge_id)
                        result = self._process_v2_label_response(response_data)
                        if result:
                            v2_success = True
                            shipment_id, label_bytes, tracking_number, cost = result
                            self.shipstation_shipment_id = shipment_id
                            shipment_cost += cost
                            final_tracking_number.append(tracking_number)
                            label_datas.append(label_bytes)
                            tracking_message = (_("Shipstation V2 Tracking Number: %s") % tracking_number)
                            self.message_post(body=tracking_message)
                            package_id.response_message = "Successfully Label Generated (V2)"
                            package_id.custom_tracking_number = tracking_number
                            package_id.shipstation_shipment_id = shipment_id
                            logmessage = _("<b>Tracking Numbers: %s") % tracking_number
                            self.message_post(body=logmessage, attachments=[("%s.pdf" % self.id, label_bytes)])
                        else:
                            logging.warning("V2 label failed for package %s, falling back to V1", package_id.id)
                    except Exception as e:
                        logging.warning("V2 label exception for package %s, falling back to V1: %s", package_id.id, e)

                if not v2_success:
                    # V1 fallback
                    body = carrier_id.generate_label_from_shipstation(self, package_id, weight, shipstation_charge=self.shipstation_shipping_charge_id)
                    response_data = carrier_id.api_calling_function("/orders/createlabelfororder", body)
                    if response_data.status_code == 200:
                        responses = response_data.json()
                        shipment_id = responses.get('shipmentId')
                        if shipment_id:
                            self.shipstation_shipment_id = shipment_id
                            label_data = responses.get('labelData')
                            tracking_number = responses.get('trackingNumber')
                            shipment_cost += responses.get('shipmentCost')
                            final_tracking_number.append(tracking_number)
                            base_data = binascii.a2b_base64(str(label_data))
                            label_datas.append(base_data)
                            tracking_message = (_("Shipstation Tracking Number: %s") % tracking_number)
                            self.message_post(body=tracking_message)
                            package_id.response_message = "Successfully Label Generated"
                            package_id.custom_tracking_number = tracking_number
                            package_id.shipstation_shipment_id = shipment_id
                            logmessage = _("<b>Tracking Numbers: %s") % tracking_number
                            label_data_pdf = binascii.a2b_base64(str(label_data))
                            self.message_post(body=logmessage, attachments=[("%s.pdf" % self.id, label_data_pdf)])
                    else:
                        error_code = "%s" % response_data.status_code
                        error_message = response_data.reason
                        error_detail = {'error': error_code + " - " + error_message + " - %s" % (response_data.text or response_data.content)}
                        package_id.response_message = error_detail
            except Exception as e:
                package_id.response_message = e
                logging.info(" Custom Code:Exception >>>>> Inside Package: %s" % e)

        if self.weight_bulk:
            try:
                weight = self.weight_bulk

                v2_success = False
                if use_v2:
                    try:
                        response_data = self.carrier_id.generate_label_from_shipstation_v2(
                            self, False, weight, shipstation_charge=self.shipstation_shipping_charge_id)
                        result = self._process_v2_label_response(response_data)
                        if result:
                            v2_success = True
                            shipment_id, label_bytes, tracking_number, cost = result
                            self.shipstation_shipment_id = shipment_id
                            shipment_cost += cost
                            final_tracking_number.append(tracking_number)
                            label_datas.append(label_bytes)
                            tracking_message = (_("Shipstation V2 Tracking Number: %s") % tracking_number)
                            self.message_post(body=tracking_message)
                            logmessage = _("<b>Tracking Numbers: %s") % tracking_number
                            self.message_post(body=logmessage, attachments=[("%s.pdf" % self.id, label_bytes)])
                        else:
                            logging.warning("V2 bulk label failed, falling back to V1")
                    except Exception as e:
                        logging.warning("V2 bulk label exception, falling back to V1: %s", e)

                if not v2_success:
                    # V1 fallback
                    body = self.carrier_id and self.carrier_id.generate_label_from_shipstation(self, False, weight, shipstation_charge=self.shipstation_shipping_charge_id)
                    response_data = self.carrier_id.api_calling_function("/orders/createlabelfororder", body)
                    if response_data.status_code == 200:
                        responses = response_data.json()
                        shipment_id = responses.get('shipmentId')
                        if shipment_id:
                            self.shipstation_shipment_id = shipment_id
                            label_data = responses.get('labelData')
                            tracking_number = responses.get('trackingNumber')
                            shipment_cost += responses.get('shipmentCost')
                            final_tracking_number.append(tracking_number)
                            base_data = binascii.a2b_base64(str(label_data))
                            label_datas.append(base_data)
                            tracking_message = (_("Shipstation Tracking Number: %s") % tracking_number)
                            self.message_post(body=tracking_message)
                            logmessage = _("<b>Tracking Numbers: %s") % tracking_number
                            label_data_pdf = binascii.a2b_base64(str(label_data))
                            self.message_post(body=logmessage, attachments=[("%s.pdf" % self.id, label_data_pdf)])
                    else:
                        error_code = "%s" % response_data.status_code
                        error_message = response_data.reason
                        error_detail = {'error': error_code + " - " + error_message + " - %s" % (response_data.json())}
                        self.message_post(body=self._format_message_body(error_detail))

            except Exception as e:
                self.message_post(body=self._format_message_body(e))
                logging.info(" Custom Code:Exception >>> Inside Bulk Weight: %s" % e)

        if not final_tracking_number:
            raise ValidationError("{}".format(error_detail))
        self.carrier_tracking_ref = ','.join(final_tracking_number)
        self.shipment_cost = shipment_cost

        file_data_temp = pdf.merge_pdf(label_datas)
        file_data_temp = base64.b64encode(file_data_temp)

        att_id = self.env['ir.attachment'].create({'name': "Wave -%s.pdf" % (file_name or ""), 'type': 'binary', 'datas': file_data_temp or "", 'mimetype': 'application/pdf', 'res_model': 'stock.picking', 'res_id': self.id, 'res_name': self.name})

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download_document?model=ir.attachment&field=datas&id=%s&filename=%s.pdf' % (att_id.id, self.name.replace('/', '_')),
            'target': 'self'
        }

    def _format_message_body(self, body):
        if isinstance(body, str):
            return body
        try:
            return json.dumps(body)
        except Exception:
            return repr(body)

    def _prepare_picking_for_immediate_transfer(self):
        self.ensure_one()
        # If still in draft => confirm and assign
        if self.state == 'done':
            logging.info(" Custom Code:%s (Backend Process) : Could not process. Picking already in DONE state." % self.name)
            return False
        if self.state == 'draft':
            self.action_confirm()
            if self.state != 'assigned':
                self.action_assign()
                if self.state != 'assigned':
                    logging.info(
                        "%s (Backend Process) : Could not reserve all requested products. Please use the \'Check Availability\' button to handle the reservation manually." % self.name)
                    return False

        # set product done qty = product uom qty.
        if self.state == 'assigned':
            for move in self.move_ids:
                for move_line in move.move_line_ids:
                    move_line.qty_done = move_line.product_uom_qty
            if self._check_backorder():
                logging.info(
                    "Custom Code: %s (Backend Process) : Could not transfer because there is a possibility of BackOrder. Please check delivery order." % self.name)
                for move in self.move_ids:
                    for move_line in move.move_line_ids:
                        move_line.product_uom_qty = move_line.qty_done
                        move_line.qty_done = 0
                return False
        else:
            logging.info(
                "{} (Backend Process) : Could not process the picking because state is not as expected '{}'.".format(
                    self.name, self.state))
            return False
        return True

    def import_delivery_order_using_cron(self):
        shipstation_operation_detail = self.env['shipstation.operation.detail']
        operation_id = shipstation_operation_detail.create({
            'shipstation_operation': 'shipment', 'shipstation_operation_type': 'import',
            'message': 'Shipstation Shipment Importing...',
        })
        pickings = self.search([('state', '=', 'done'),
                                ('is_order_imported_in_shipstation', '=', False),
                                ('shipstation_order_id', '!=', ''),
                                ('picking_type_code', '=', 'outgoing')])
        logging.info(" Custom Code:Total PICKING : {0} >>>>>>>>>>>>>> Pickings : {1}".format(len(pickings), pickings))
        for picking in pickings:
            picking.sudo().import_delivery_order(operation_id)

        operation_id and operation_id.write({'message': 'Shipstation Shipment Import Process Done Successfully.', })
        logging.info(" Custom Code:Shipstation Import delivery order Cron Finished")
        return True

    def import_delivery_order(self, operation_id=False):
        self.ensure_one()
        shipstation_operation_details = self.env['shipstation.operation.details']
        try:
            configuration = self.shipstation_configuration_id
            if not configuration:
                configuration = self.sale_id.shipstation_configuration_id
            if not configuration:
                configuration = self.env['shipstation.odoo.configuration.vts'].search([], limit=1)
            if not configuration:
                shipstation_operation_details.create(
                    {'operation_id': operation_id and operation_id.id,
                     'shipstation_response_message': "Shipstation Configuration Missing",
                     'fault_operaion': True,
                     'shipstation_operation': 'shipment'})
                return
            ref_number = self.shipstation_sale_order_number
            shipstation_sale_order_number = ref_number.replace("#", "%23")
            url = configuration.making_shipstation_url('/shipments?orderNumber=%s' % (shipstation_sale_order_number))
            api_secret = configuration.api_secret
            api_key = configuration.api_key
            data = "%s:%s" % (api_key, api_secret)
            encode_data = base64.b64encode(data.encode("utf-8"))
            authrization_data = "Basic %s" % (encode_data.decode("utf-8"))
            headers = {"Authorization": authrization_data,
                       "Content-Type": "application/json"}
            try:
                response_data = request(method='GET', url=url, headers=headers)
            except Exception as e:
                shipstation_operation_details.create(
                    {'operation_id': operation_id and operation_id.id,
                     'shipstation_response_message': "Shipstation Import Order Issue %s, %s" % (self.name, e),
                     'fault_operaion': True,
                     'shipstation_operation': 'shipment'})
                return

            if response_data.status_code == 200:
                responses = response_data.json()
                shipments = responses.get('shipments')
                if not shipments:
                    shipstation_operation_details.create(
                        {'operation_id': operation_id and operation_id.id,
                         'shipstation_response_message': "%s Data is not availabel. %s" % (self.name, responses),
                         'fault_operaion': True,
                         'shipstation_operation': 'shipment'})
                    return
                if isinstance(shipments, dict):
                    shipments = [shipments]
                shipment_tracking_number = []
                shipstation_batch_numbers = []
                shipstation_carrier_codes = []
                shipstation_unit_of_measures = []
                shipment_ids = []
                service_code = []
                total_shipping_cost = 0.0
                total_shipstation_weight = 0.0
                customField_deatils = ""
                for shipment in shipments:
                    logging.info(" Custom Code:>>>>>>>> ORDER SHIPMENT : {}".format(shipment))
                    if shipment.get('voided') != True:
                        logging.info(" Custom Code:Insided not voided")
                        tracking_number = shipment.get('trackingNumber')
                        shipping_cost = shipment.get('shipmentCost')
                        service = shipment.get('serviceCode')
                        shipment_id = shipment.get('shipmentId')
                        shipstation_weight = shipment.get('weight').get('value')
                        shipstation_unit_of_measure = shipment.get('weight').get('units')
                        shipstation_carrier_code = shipment.get('carrierCode')
                        shipstation_batch_number = shipment.get('batchNumber')
                        service_code.append("%s-%s" % (service, tracking_number))
                        shipment_ids.append("%s" % shipment_id)
                        total_shipping_cost += float(shipping_cost)
                        total_shipstation_weight += float(shipstation_weight)
                        shipment_tracking_number.append(tracking_number)
                        shipstation_batch_numbers.append(shipstation_batch_number)
                        shipstation_carrier_codes.append(shipstation_carrier_code)
                        shipstation_unit_of_measures.append(shipstation_unit_of_measure)

                self.carrier_tracking_ref = ','.join(shipment_tracking_number)
                self.shipstation_service_code = ','.join(service_code)
                self.carrier_price = total_shipping_cost
                self.is_order_imported_in_shipstation = True
                self.shipstation_shipment_id = ','.join(shipment_ids)
                self.shipstation_weight = total_shipstation_weight
                self.shipstation_unit_of_measure = ','.join(shipstation_unit_of_measures)
                self.shipstation_carrier_code = ','.join(shipstation_carrier_codes)
                # self.shipstation_batch_number = ','.join(shipstation_batch_numbers)
                # self.order_custom_data = customField_deatils

                shipstation_operation_details.sudo().create(
                    {'operation_id': operation_id and operation_id.id,
                     'shipstation_request_message': "URL : %s" % (url),
                     'shipstation_response_message': "%s Delivery Order Information Imported Successfully, Order ID : %s, Tracking Number : %s, Shipping Cost : %s " % (
                     self.name, self.shipstation_order_id, ','.join(shipment_tracking_number), total_shipping_cost),
                     'fault_operaion': False,
                     'shipstation_operation': 'shipment'})
                # self.action_done()
                self._cr.commit()
                logging.info(" Custom Code:Shipment Data Imported For This Picking : %s." % (self.name))
            else:
                error_code = "%s" % (response_data.status_code)
                error_message = response_data.reason
                error_detail = {'error': error_code + " - " + error_message + " - "}
                if response_data.json():
                    error_detail = {'error': error_code + " - " + error_message + " - %s" % (response_data.json())}
                shipstation_operation_details.sudo().create(
                    {'operation_id': operation_id and operation_id.id,
                     'shipstation_response_message': "%s Delivery order Not Imported %s" % (self.name, error_detail),
                     'fault_operaion': True,
                     'shipstation_operation': 'shipment'})
        except Exception as e:
            shipstation_operation_details.sudo().create(
                {'operation_id': operation_id and operation_id.id,
                 'shipstation_response_message': "%s Delivery order Not Imported %s" % (self.name, e),
                 'fault_operaion': True,
                 'shipstation_operation': 'shipment'})
