import base64
import binascii
import json
import logging
from requests import request
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from odoo.tools import pdf


class ShipstationPackageDetails(models.Model):
    _inherit = "stock.quant.package"

    @api.model
    def _default_carrier_from_context(self):
        ctx = self.env.context
        if ctx.get("default_carrier_id"):
            carrier = self.env["delivery.carrier"].browse(ctx["default_carrier_id"])
            return carrier.id if carrier.exists() else False

        picking = False
        if ctx.get("default_picking_id"):
            picking = self.env["stock.picking"].browse(ctx["default_picking_id"])
        elif ctx.get("active_model") == "stock.picking" and ctx.get("active_id"):
            picking = self.env["stock.picking"].browse(ctx["active_id"])

        if picking and picking.exists() and picking.carrier_id:
            return picking.carrier_id.id
        return False

    @api.model
    def _default_shipstation_package_from_context(self):
        ctx = self.env.context
        if ctx.get("default_shipstation_delivery_package_id"):
            pkg = self.env["shipstation.delivery.package"].browse(ctx["default_shipstation_delivery_package_id"])
            return pkg.id if pkg.exists() else False

        picking = False
        if ctx.get("default_picking_id"):
            picking = self.env["stock.picking"].browse(ctx["default_picking_id"])
        elif ctx.get("active_model") == "stock.picking" and ctx.get("active_id"):
            picking = self.env["stock.picking"].browse(ctx["active_id"])

        if picking and picking.exists() and getattr(picking, "delivery_package_id", False):
            return picking.delivery_package_id.id
        return False

    custom_tracking_number = fields.Char(
        string="Shipstation Tracking Number",
        help="If tracking number available print it in this field.")
    is_generate_label_in_shipstation = fields.Boolean(
        default=True,
        string="Is Generate Label In Shipstation.?",
        help="If user do not need to generate the label then we need to Set value false.")
    response_message = fields.Char(string="Response Message")
    carrier_id = fields.Many2one(
        "delivery.carrier",
        string="Carrier",
        default=lambda self: self._default_carrier_from_context(),
    )
    shipstation_shipment_id = fields.Char(
        string="Shipstation Shipment",
        help="Shipstation Shipment ID.", copy=False)
    length = fields.Float(string='Length', help='Package length in inches')
    width = fields.Float(string='Width', help='Package width in inches')
    height = fields.Float(string='Height', help='Package height in inches')
    shipstation_delivery_package_id = fields.Many2one(
        "shipstation.delivery.package",
        string="ShipStation Delivery Package",
        default=lambda self: self._default_shipstation_package_from_context(),
    )
    minimum_weight = fields.Float(
        string='Min Weight',
        compute='_compute_minimum_weight',
        help='Minimum weight based on product weights.')

    @api.depends('quant_ids', 'quant_ids.quantity', 'quant_ids.product_id')
    def _compute_minimum_weight(self):
        for package in self:
            total = 0.0
            for quant in package.quant_ids:
                total += quant.quantity * (quant.product_id.weight or 0.0)
            package.minimum_weight = round(total, 3)

    @api.constrains('shipping_weight')
    def _check_minimum_weight(self):
        for package in self:
            if package.shipping_weight and package.minimum_weight:
                if package.shipping_weight < package.minimum_weight:
                    raise ValidationError(
                        _("Shipping weight (%(weight)s) cannot be less than the minimum "
                          "product weight (%(min_weight)s) for package %(name)s.") % {
                            'weight': package.shipping_weight,
                            'min_weight': package.minimum_weight,
                            'name': package.name,
                        }
                    )

    def _find_picking(self):
        """Find the stock.picking this package belongs to."""
        self.ensure_one()
        # Try package_level first
        package_level = self.env['stock.package_level'].search([
            ('package_id', '=', self.id)
        ], limit=1)
        if package_level and package_level.picking_id:
            return package_level.picking_id
        # Fallback: find via move lines
        move_line = self.env['stock.move.line'].search([
            ('result_package_id', '=', self.id)
        ], limit=1)
        if move_line and move_line.picking_id:
            return move_line.picking_id
        return self.env['stock.picking']

    def action_generate_single_label(self):
        """Generate a ShipStation shipping label for this single package.

        Follows the same flow as bulk label generation:
        1. Require a shipping service to be selected (via Check Rates)
        2. Create ShipStation order if needed
        3. Generate label via V2 or V1 API
        """
        self.ensure_one()
        logging.info(
            "ShipStation single-label START: package_id=%s name=%s carrier_id=%s shipstation_delivery_package_id=%s "
            "dims(in)=%sx%sx%s shipping_weight=%s min_weight=%s",
            self.id,
            self.name,
            self.carrier_id.id if self.carrier_id else False,
            self.shipstation_delivery_package_id.id if self.shipstation_delivery_package_id else False,
            self.length,
            self.width,
            self.height,
            self.shipping_weight,
            self.minimum_weight,
        )

        picking = self._find_picking()
        if not picking:
            raise ValidationError(_("Cannot find the delivery order for this package."))

        logging.info(
            "ShipStation single-label: resolved picking_id=%s name=%s state=%s carrier_id=%s shipstation_charge_id=%s",
            picking.id,
            picking.name,
            picking.state,
            picking.carrier_id.id if picking.carrier_id else False,
            picking.shipstation_shipping_charge_id.id if picking.shipstation_shipping_charge_id else False,
        )

        # Resolve carrier: package carrier > picking carrier
        carrier = self.carrier_id or picking.carrier_id
        if not carrier:
            raise ValidationError(
                _("No delivery carrier found. Please set a carrier on the package or on "
                  "the delivery order '%s'.") % picking.name)

        logging.info(
            "ShipStation single-label: using carrier_id=%s name=%s delivery_type=%s shipstation_config_id=%s",
            carrier.id,
            carrier.name,
            getattr(carrier, "delivery_type", None),
            getattr(carrier, "shipstation_configuration_id", False) and carrier.shipstation_configuration_id.id or False,
        )

        # Ensure picking has the carrier set (needed for rate checking)
        if not picking.carrier_id and self.carrier_id:
            picking.carrier_id = self.carrier_id
            logging.info(
                "ShipStation single-label: picking carrier_id set from package: picking_id=%s carrier_id=%s",
                picking.id,
                picking.carrier_id.id,
            )

        # Require a shipping service to be selected first (same as bulk flow)
        shipstation_charge = picking.shipstation_shipping_charge_id
        if not shipstation_charge:
            # Redirect to the rate checking wizard so user can pick a service
            logging.info(
                "ShipStation single-label: NO selected rate on picking. Redirecting to rate wizard with package context. "
                "picking_id=%s package_id=%s",
                picking.id,
                self.id,
            )
            return picking.with_context(shipstation_package_id=self.id).button_check_shipstation_rates()

        logging.info(
            "ShipStation single-label: selected rate charge_id=%s provider=%s service_code=%s service_name=%s v2_rate_id=%s",
            shipstation_charge.id,
            getattr(shipstation_charge, "shipstation_provider", None),
            getattr(shipstation_charge, "shipstation_service_code", None),
            getattr(shipstation_charge, "shipstation_service_name", None),
            getattr(shipstation_charge, "v2_rate_id", None),
        )

        logging.info(
            "Generating single label: package=%s, picking=%s, carrier=%s, charge=%s",
            self.name, picking.name, carrier.name,
            shipstation_charge.shipstation_service_name if shipstation_charge else 'None')

        weight = self.shipping_weight
        if not weight:
            raise ValidationError(
                _("Please set a shipping weight on package '%s'.") % self.name)

        # Log what we'll actually send (dimensions resolved via carrier helper, weight converted in carrier)
        try:
            resolved_dims = {
                "length": carrier._resolve_label_dimension(picking, self, "length"),
                "width": carrier._resolve_label_dimension(picking, self, "width"),
                "height": carrier._resolve_label_dimension(picking, self, "height"),
            }
            converted_weight = carrier.get_total_weight(weight)
            logging.info(
                "ShipStation single-label: resolved shipment inputs package_id=%s weight_raw=%s weight_converted=%s "
                "weight_uom=%s dim_uom=%s dims=%s",
                self.id,
                weight,
                converted_weight,
                getattr(carrier, "weight_uom", None),
                getattr(carrier, "shipstation_dimentions", None),
                resolved_dims,
            )
        except Exception as e:
            logging.warning("ShipStation single-label: failed to resolve/log dims/weight details: %s", e)

        # Ensure ShipStation order exists (V1 requires orderId)
        if not picking.shipstation_order_id:
            logging.info("Creating ShipStation order for picking %s", picking.name)
            try:
                body = carrier.create_or_update_order(picking)
                logging.info(
                    "ShipStation single-label: order create/update request prepared (picking_id=%s carrier_id=%s)",
                    picking.id, carrier.id
                )
                response_data = carrier.api_calling_function("/orders/createorder", body)
                if response_data.status_code == 200:
                    responses = response_data.json()
                    order_id = responses.get('orderId')
                    order_key = responses.get('orderKey')
                    order_number = responses.get('orderNumber')
                    if order_id:
                        picking.write({
                            'shipstation_order_id': order_id,
                            'shipstation_order_key': order_key,
                            'shipstation_sale_order_number': order_number,
                            'shipstation_configuration_id': carrier.shipstation_configuration_id.id,
                        })
                        if picking.sale_id and not picking.sale_id.shipstation_order_number:
                            picking.sale_id.shipstation_order_number = order_number
                            picking.sale_id.shipstation_order_id = order_id
                            picking.sale_id.shipstation_configuration_id = carrier.shipstation_configuration_id.id
                            picking.sale_id.is_exported_to_shipstation = True
                            picking.sale_id.shipstation_store_id = carrier.store_id.id if carrier.store_id else False
                        logging.info("ShipStation order created: orderId=%s", order_id)
                    else:
                        raise ValidationError(
                            _("ShipStation order creation returned no orderId."))
                else:
                    raise ValidationError(
                        _("ShipStation order creation failed: %s - %s") % (
                            response_data.status_code,
                            response_data.text or response_data.reason))
            except ValidationError:
                raise
            except Exception as e:
                logging.exception("ShipStation single-label: order creation exception (picking_id=%s)", picking.id)
                raise ValidationError(
                    _("Failed to create ShipStation order: %s") % e)

        use_v2 = picking._is_v2_enabled()
        logging.info(
            "ShipStation single-label: v2_enabled=%s picking_order_id=%s picking_order_key=%s",
            bool(use_v2),
            picking.shipstation_order_id,
            picking.shipstation_order_key,
        )
        label_bytes = None
        tracking_number = None
        shipment_id = None
        cost = 0.0

        # Try V2 first
        if use_v2:
            try:
                response_data = carrier.generate_label_from_shipstation_v2(
                    picking, self, weight,
                    shipstation_charge=shipstation_charge)
                logging.info(
                    "ShipStation single-label: V2 label response status=%s (package_id=%s)",
                    getattr(response_data, "status_code", None),
                    self.id,
                )
                result = picking._process_v2_label_response(response_data)
                if result:
                    shipment_id, label_bytes, tracking_number, cost = result
                    logging.info("V2 label OK for package %s: tracking=%s", self.name, tracking_number)
            except Exception as e:
                logging.exception("V2 single label failed for package %s: %s", self.id, e)

        # V1 fallback
        if not label_bytes:
            try:
                body = carrier.generate_label_from_shipstation(
                    picking, self, weight,
                    shipstation_charge=shipstation_charge)
                logging.info(
                    "ShipStation single-label: V1 label request prepared (picking_id=%s package_id=%s)",
                    picking.id,
                    self.id,
                )
                response_data = carrier.api_calling_function(
                    "/orders/createlabelfororder", body)
                logging.info(
                    "ShipStation single-label: V1 label response status=%s (package_id=%s)",
                    getattr(response_data, "status_code", None),
                    self.id,
                )
                if response_data.status_code == 200:
                    responses = response_data.json()
                    shipment_id = responses.get('shipmentId')
                    label_data = responses.get('labelData')
                    tracking_number = responses.get('trackingNumber')
                    cost = responses.get('shipmentCost', 0.0)
                    label_bytes = binascii.a2b_base64(str(label_data))
                    logging.info("V1 label OK for package %s: tracking=%s", self.name, tracking_number)
                else:
                    raise ValidationError(
                        _("Label generation failed: %s - %s") % (
                            response_data.status_code,
                            response_data.text or response_data.reason))
            except ValidationError:
                raise
            except Exception as e:
                logging.exception("ShipStation single-label: V1 label exception (package_id=%s)", self.id)
                raise ValidationError(
                    _("Label generation error for package '%s': %s") % (self.name, e))

        if not label_bytes or not tracking_number:
            raise ValidationError(_("Failed to generate label for package '%s'.") % self.name)

        # Update package
        self.response_message = "Successfully Label Generated"
        self.custom_tracking_number = tracking_number
        self.shipstation_shipment_id = shipment_id

        # Update picking
        picking.shipstation_shipment_id = shipment_id
        picking.shipment_cost = (picking.shipment_cost or 0.0) + cost
        existing_refs = (picking.carrier_tracking_ref or '').split(',')
        existing_refs = [r for r in existing_refs if r]
        existing_refs.append(tracking_number)
        picking.carrier_tracking_ref = ','.join(existing_refs)

        # Post tracking message
        picking.message_post(
            body=_("ShipStation Tracking for %s: %s") % (self.name, tracking_number),
            attachments=[("%s.pdf" % self.name, label_bytes)])

        logging.info(
            "ShipStation single-label SUCCESS: package_id=%s shipment_id=%s tracking=%s cost=%s",
            self.id,
            shipment_id,
            tracking_number,
            cost,
        )

        # Return download action
        file_data = base64.b64encode(label_bytes)
        att = self.env['ir.attachment'].create({
            'name': "Label-%s.pdf" % (self.name or ""),
            'type': 'binary',
            'datas': file_data,
            'mimetype': 'application/pdf',
            'res_model': 'stock.quant.package',
            'res_id': self.id,
            'res_name': self.name,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download_document?model=ir.attachment&field=datas&id=%s&filename=%s.pdf' % (
                att.id, (self.name or 'label').replace('/', '_')),
            'target': 'self',
        }

    def action_download_latest_label(self):
        """Download the most recent shipping label for this package."""
        self.ensure_one()
        att = self.env['ir.attachment'].search([
            ('res_model', '=', 'stock.quant.package'),
            ('res_id', '=', self.id),
            ('name', 'like', 'Label-'),
            ('mimetype', '=', 'application/pdf'),
        ], order='id desc', limit=1)
        if not att:
            raise ValidationError(
                _("No label found for package '%s'.") % self.name)
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download_document?model=ir.attachment&field=datas&id=%s&filename=%s.pdf' % (
                att.id, (self.name or 'label').replace('/', '_')),
            'target': 'self',
        }

    def api_calling_function(self, url_data, body):
        configuration = self.env['shipstation.odoo.configuration.vts'].search([], limit=1)
        if not configuration:
            raise ValidationError("Configuration Not Done.")
        url = configuration.making_shipstation_url(url_data)
        api_secret = configuration.api_secret
        api_key = configuration.api_key
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

    def shipstation_cancel_shipment(self):
        shipment_id = self.shipstation_shipment_id
        if not shipment_id:
            raise ValidationError("Shipstation Shipment Id Not Available!")
        req_data = {"shipmentId": shipment_id}
        try:
            response_data = self.api_calling_function("/shipments/voidlabel", req_data)
            if response_data.status_code == 200:
                responses = response_data.json()
                logging.info(" Custom Code:Response Data: %s" % (responses))
                approved = responses.get('approved')
                if approved:
                    return {
                        'effect': {
                            'fadeout': 'slow',
                            'message': 'Shipment Cancelled In Shipstation %s' % (shipment_id),
                            'img_url': '/web/static/img/smile.svg',
                            'type': 'rainbow_man',
                        }
                    }
            else:
                error_code = "%s" % (response_data.status_code)
                error_message = response_data.reason
                error_detail = {'error': error_code + " - " + error_message + " - "}
                if response_data.json():
                    error_detail = {'error': error_code + " - " + error_message + " - %s" % (response_data.json())}
                raise ValidationError(error_detail)
        except Exception as e:
            raise ValidationError(e)
