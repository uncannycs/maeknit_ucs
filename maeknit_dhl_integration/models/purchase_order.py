import logging
import requests
import math
from lxml import etree
from datetime import datetime, timedelta
from odoo.exceptions import UserError
from odoo import fields, api, models, _

_logger = logging.getLogger(__name__)

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.model
    def _default_picking_type(self):
        return self._get_picking_type(self.env.context.get('company_id') or self.env.company.id)

    dhl_shipping_estimate = fields.Monetary(string="DHL Shipping Estimate", currency_field='currency_id', tracking=True, copy=False)
    duty_tax_estimate = fields.Monetary(string="Duty/Tax Estimate", currency_field='currency_id', tracking=True, copy=False)
    total_landed_cost = fields.Monetary(string="Total Landed Cost", compute='_compute_total_landed_cost', store=True, tracking=True, copy=False)
    
    dhl_account_number = fields.Char(string="DHL Account Number", copy=False)
    
    is_estimate_frozen = fields.Boolean(string="Estimate Frozen", default=False, copy=False)

    total_weight = fields.Float(string="Total Weight (kg)", compute='_compute_total_weight', store=True, readonly=False, copy=False)
    product_subtotal = fields.Float(string="Product Subtotal", copy=False)
    shipment_purpose = fields.Selection([('gift', 'Gift'), ('commercial', 'Commercial'), ('personal', 'Personal,Not for sale'), ('sample', 'Sample'),
                                         ('return_for_repair', 'Return For Repair'), ('return_after_repair', 'Return After Repair'),
                                         ('claim', 'Claim'), ('return_to_seller', 'Return To Seller')], default='sample', string='Purpose of Shipment', copy=False, required=True)
    picking_type_id = fields.Many2one('stock.picking.type', 'Deliver To', required=True, default=_default_picking_type,
                                      domain="[('code', 'in', ('incoming', 'dropship')), '|', ('warehouse_id', '=', False), ('warehouse_id.company_id', 'in', allowed_company_ids)]",
                                      help="This will determine operation type of incoming shipment")


    @api.depends('order_line.product_id', 'order_line.product_qty')
    def _compute_total_weight(self):
        for order in self:
            weight = 0.0
            for line in order.order_line:
                if line.product_id:
                    # Fetching weight directly from the product record
                    weight += line.product_id.weight * line.product_qty
            order.total_weight = weight

    @api.depends('order_line.price_total', 'dhl_shipping_estimate', 'duty_tax_estimate')
    def _compute_total_landed_cost(self):
        for order in self:
            product_total = 0.0

            for line in order.order_line:
                if line.product_id.type != 'service':
                    product_total += line.price_total

            order.product_subtotal = product_total
            order.total_landed_cost = order.product_subtotal + order.dhl_shipping_estimate + order.duty_tax_estimate

    def button_confirm(self):
        res = super(PurchaseOrder, self).button_confirm()
        for order in self:
            order.is_estimate_frozen = True
        return res
        
    def action_get_dhl_quote(self):
        self.ensure_one()
        if self.is_estimate_frozen:
            raise UserError(_("Estimates are frozen for confirmed orders."))
        
        # 1. Prepare and Validate data
        shipper = self.partner_id  # Vendor
        recipient = self.dest_address_id or self.picking_type_id.warehouse_id.partner_id
        # Strict validation for DHL requirements
        missing_shipper = [f for f in ['zip', 'country_id', 'city', 'phone'] if not shipper[f]]
        if missing_shipper:
            raise UserError(_("Vendor (Shipper) information is incomplete. Missing: %s") % ", ".join(missing_shipper))
            
        missing_recipient = [f for f in ['zip', 'country_id', 'city', 'phone'] if not recipient[f]]
        if missing_recipient:
            raise UserError(_("Destination (Recipient) information is incomplete. Missing: %s") % ", ".join(missing_recipient))
            
        if self.total_weight <= 0:
            raise UserError(_("Total weight must be greater than 0."))

        pieces_xml = ""
        piece_id = 1
        MAX_PIECES = 100
        total_weight_remaining = self.total_weight

        stop_pieces = False
        for index, line in enumerate(self.order_line):
            if stop_pieces:
                break
            if not line.product_id or line.product_id.type == 'service':
                continue

            # Try to find packaging definition
            packaging = line.product_packaging_id or (
                    line.product_id.packaging_ids and line.product_id.packaging_ids[0])

            pkg_type = packaging.package_type_id if packaging else False
            if pkg_type:
                # Get dimensions from stock.package.type
                h = (pkg_type.height or 10) / 10
                w = (pkg_type.width or 10) / 10
                l = (pkg_type.packaging_length or 10) / 10

                qty_per_pkg = packaging.qty or 1.0
                num_pkgs = math.ceil(line.product_qty / qty_per_pkg)

                remaining_qty = line.product_qty
                for i in range(num_pkgs):
                    if piece_id >= MAX_PIECES:
                        # Consolidate ALL remaining weight into the last piece
                        pieces_xml += f"""
                        <Piece>
                          <PieceID>{piece_id}</PieceID>
                          <PackageTypeCode>BOX</PackageTypeCode>
                          <Height>30</Height>
                          <Depth>30</Depth>
                          <Width>30</Width>
                          <Weight>{max(0.1, self.total_weight):.3f}</Weight>
                        </Piece>"""
                        piece_id += 1
                        stop_pieces = True
                        break

                    pkg_qty = min(remaining_qty, qty_per_pkg)
                    pkg_weight = pkg_qty * (line.product_id.weight or 0.1)

                    pieces_xml += f"""
                        <Piece>
                          <PieceID>{piece_id}</PieceID>
                          <PackageTypeCode>BOX</PackageTypeCode>
                          <Height>{int(h)}</Height>
                          <Depth>{int(l)}</Depth>
                          <Width>{int(w)}</Width>
                          <Weight>{self.total_weight:.3f}</Weight>
                        </Piece>"""
                    piece_id += 1
                    remaining_qty -= pkg_qty
                    total_weight_remaining -= pkg_weight

            else:
                # Fallback for items without packaging: 1 piece per line
                if piece_id >= MAX_PIECES:
                    pieces_xml += f"""
                        <Piece>
                          <PieceID>{piece_id}</PieceID>
                          <PackageTypeCode>BOX</PackageTypeCode>
                          <Height>30</Height>
                          <Depth>30</Depth>
                          <Width>30</Width>
                          <Weight>{max(0.1, self.total_weight):.3f}</Weight>
                        </Piece>"""
                    piece_id += 1
                    stop_pieces = True

                else:
                    weight = line.product_qty * (line.product_id.weight or 0.1)
                    pieces_xml += f"""
                        <Piece>
                          <PieceID>{piece_id}</PieceID>
                          <PackageTypeCode>BOX</PackageTypeCode>
                          <Height>10</Height>
                          <Depth>10</Depth>
                          <Width>10</Width>
                          <Weight>{self.total_weight:.3f}</Weight>
                        </Piece>"""
                    piece_id += 1
                    total_weight_remaining -= weight


        if not pieces_xml:
            # Absolute fallback if somehow no pieces were generated
            pieces_xml = f"""
                        <Piece>
                          <PieceID>1</PieceID>
                          <PackageTypeCode>BOX</PackageTypeCode>
                          <Height>10</Height>
                          <Depth>10</Depth>
                          <Width>10</Width>
                          <Weight>{self.total_weight:.3f}</Weight>
                        </Piece>"""


        # 2. Call DHL API
        company = self.company_id
        if not company.dhl_site_id or not company.dhl_password or not company.dhl_account_number:
            raise UserError(_("Please complete DHL configuration (SiteID, Password, and Account Number) in Company settings."))

        _logger.info("DHL Quote Request (PO %s) for products: %s", self.id, self.order_line.mapped('product_id.display_name'))
        
        if company.dhl_use_production:
            url = "https://xmlpi-ea.dhl.com/XMLShippingServlet"
        else:
            url = "https://xmlpitest-ea.dhl.com/XMLShippingServlet?isUTF8Support=true"
            
        is_dutiable = 'Y' if shipper.country_id != recipient.country_id else 'N'
        
        now = datetime.now()
        # Start looking from today, but use a very early cutoff (8 AM UTC) to shift to tomorrow for safety
        # Start looking from tomorrow by default to avoid pickup window closure errors in different timezones
        pickup_date = now.date() + timedelta(days=1)
        
        all_errors = []
        try:
            for attempt in range(4): # Try current/planned date + up to 3 more days
                # Skip weekends
                while pickup_date.weekday() >= 5:
                    pickup_date += timedelta(days=1)
                
                # ReadyTime PT05H00M (5 AM local) is very safe for most global pickup windows
                ready_time = "PT05H00M" 
                
                # SCHEMA CRITICAL: The order of elements in <Piece> MUST be:
                # PieceID -> PackageTypeCode -> Height -> Depth -> Width -> Weight
                xml_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:DCTRequest xmlns:p="http://www.dhl.com" xmlns:p1="http://www.isd.dpdhl.com/DCTRequestDataTypes" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.dhl.com DCT-req.xsd ">
  <GetQuote>
    <Request>
      <ServiceHeader>
        <MessageTime>{now.isoformat()}</MessageTime>
        <MessageReference>DHL-REF-PO-{self.id}-{now.strftime('%Y%m%d%H%M%S')}-{attempt}</MessageReference>
        <SiteID>{company.dhl_site_id}</SiteID>
        <Password>{company.dhl_password}</Password>
      </ServiceHeader>
    </Request>
    <From>
      <CountryCode>{(shipper.country_id.code or '').strip()}</CountryCode>
      <Postalcode>{(shipper.zip or '').strip()}</Postalcode>
      <City>{(shipper.city or '').strip()}</City>
    </From>
    <BkgDetails>
      <PaymentCountryCode>{(recipient.country_id.code or '').strip()}</PaymentCountryCode>
      <Date>{pickup_date.strftime('%Y-%m-%d')}</Date>
      <ReadyTime>{ready_time}</ReadyTime>
      <ReadyTimeGMTOffset>+00:00</ReadyTimeGMTOffset>
      <DimensionUnit>CM</DimensionUnit>
      <WeightUnit>KG</WeightUnit>
      <Pieces>{pieces_xml}
      </Pieces>
      <PaymentAccountNumber>{(company.dhl_account_number or '').strip()}</PaymentAccountNumber>
      <IsDutiable>{is_dutiable}</IsDutiable>
      <NetworkTypeCode>TD</NetworkTypeCode>
    </BkgDetails>
    <To>
      <CountryCode>{(recipient.country_id.code or '').strip()}</CountryCode>
      <Postalcode>{(recipient.zip or '').strip()}</Postalcode>
      <City>{(recipient.city or '').strip()}</City>
    </To>
    <Dutiable>
      <DeclaredCurrency>{self.currency_id.name}</DeclaredCurrency>
      <DeclaredValue>{self.amount_total:.2f}</DeclaredValue>
    </Dutiable>
  </GetQuote>
</p:DCTRequest>"""

                headers = {'Content-Type': 'application/xml'}
                response = requests.post(url, data=xml_request, headers=headers, timeout=30)

                if response.status_code != 200:
                    all_errors.append(f"Day {pickup_date}: HTTP {response.status_code}")
                    pickup_date += timedelta(days=1)
                    continue

                root = etree.fromstring(response.content)
                
                # Check for Failure Status
                action_status = root.xpath("string(.//*[local-name()='ActionStatus'])")
                condition_nodes = root.xpath(".//*[local-name()='Condition']")
                
                day_errors = []
                retry_this_date = False
                for cond in condition_nodes:
                    code = cond.xpath("string(.//*[local-name()='ConditionCode'])")
                    data = cond.xpath("string(.//*[local-name()='ConditionData'])")
                    if code == '410201': # Pick-up service not provided
                        day_errors.append(f"Day {pickup_date}: Pick-up service not provided.")
                        retry_this_date = True
                        break
                    if data:
                        day_errors.append(f"Day {pickup_date}: {code}: {data}")

                if retry_this_date:
                    _logger.info("DHL Pick-up not provided on %s, trying next day...", pickup_date)
                    all_errors.extend(day_errors)
                    pickup_date += timedelta(days=1)
                    continue
                
                if day_errors:
                    all_errors.extend(day_errors)
                    pickup_date += timedelta(days=1)
                    continue
                
                if action_status == "Failure" and not day_errors:
                    all_errors.append(f"Day {pickup_date}: ActionStatus=Failure (No specific error code).")
                    pickup_date += timedelta(days=1)
                    continue
                    
                # Extract and Save Charges
                charge_nodes = root.xpath(".//*[local-name()='ShippingCharge']")
                charges = []
                for node in charge_nodes:
                    try:
                        charges.append(float(node.text))
                    except (ValueError, TypeError):
                        continue
                
                if charges:
                    max_charge = max(charges)
                    self.dhl_shipping_estimate = max_charge
                    
                    # Sync Account Number: Priority to response, fallback to company settings
                    resp_account = root.xpath("string(.//*[local-name()='PaymentAccountNumber'])")
                    if resp_account:
                        self.dhl_account_number = resp_account
                    elif company.dhl_account_number:
                        self.dhl_account_number = company.dhl_account_number
                        
                    self.message_post(body=_("DHL Quote Success: %s (Pickup Date: %s, Account: %s)") % (max_charge, pickup_date, self.dhl_account_number))
                    
                    # Auto-calculate duties as well
                    # self.action_estimate_duties()
                    self.action_get_duty_rate()
                    # self._update_dhl_po_lines()
                    
                    return # SUCCESS
                else:
                    all_errors.append(f"Day {pickup_date}: No valid charges/services returned in successful response.")
                    pickup_date += timedelta(days=1)

            # If we reached here, it failed after all attempts
            error_details = "\n".join(all_errors) if all_errors else _("Unknown reason (No error codes returned).")
            _logger.error("DHL Quote Final Failure for PO %s. Summary: %s", self.id, error_details)
            raise UserError(_("DHL Quote failed for all attempted dates.\n\nSummary of attempts:\n%s") % error_details)
            
        except Exception as e:
            if isinstance(e, UserError):
                raise e
            _logger.exception("DHL API Exception for PO %s", self.id)
            raise UserError(_("DHL API Exception: %s") % str(e))


    def action_get_duty_rate(self):
        for order in self:
            company = order.company_id
            if not company.dutify_api_key:
                _logger.warning("Missing Dutify API Key for company %s", company.name)
                continue

            # Determine destination country code
            dest_partner = order.dest_address_id or order.picking_type_id.warehouse_id.partner_id
            country_code = dest_partner.country_id.code or order.company_id.country_id.code or 'US'

            rate = 0.0
            for line in order.order_line:
                if not line.product_id or line.product_id.type == 'service':
                    continue

                product = line.product_id
                template = product.product_tmpl_id

                # Auto-generate HS Code for any storable product missing it
                if template.type != 'service' and not product.lookup_id:
                    try:
                        template.action_generate_dhl_hs_code_backend(country_code)
                    except Exception as e:
                        _logger.error("Failed to auto-generate HS code for %s: %s", product.display_name, str(e))

                # If still no lookup_id, skip this product's duty but don't block the order
                if not product.lookup_id:
                    order.message_post(body=_("Skipping duty estimate for product '%s' (Missing HS Code/Lookup ID)") % product.display_name)
                    continue

                if not product.hs_code:
                    continue

                product_hs_6 = product.hs_code[:6]

                # API CALL (example GET using lookup_id)
                url = f"https://dutify.com/api/v1/hs_lookups/{product.lookup_id}"
                headers = {
                    "accept": "application/json",
                    "X-API-KEY": company.dutify_api_key
                }

                try:
                    response = requests.get(url, headers=headers, timeout=15)
                    data = response.json()

                    for item in data.get('included', []):
                        attr = item.get('attributes', {})
                        api_hs = (attr.get('hs_code') or '')[:6]

                        if product_hs_6 == api_hs:
                            duty_rate = float(attr.get('general_rate_percent', 0.0))
                            rate += (line.price_subtotal * duty_rate) / 100
                except Exception as e:
                    _logger.error("Duty fetch failed for line %s: %s", product.display_name, str(e))

            order.duty_tax_estimate = rate
            order.message_post(body=_("Duty/Tax Estimate updated: %s") % rate)

    def _update_dhl_po_lines(self):
        """ Create or update a PO line for the DHL service product """
        self.ensure_one()
        # Search for a product that has 'is_dhl' set to True
        dhl_product = self.env['product.product'].search([('is_dhl', '=', True)], limit=1)
        if not dhl_product:
            _logger.info("No DHL product found (is_dhl=True). Skipping PO line creation.")
            return
        
        total_dhl_cost = self.dhl_shipping_estimate + self.duty_tax_estimate
        if total_dhl_cost <= 0:
            return

        # Find if a line with this product already exists
        existing_line = self.order_line.filtered(lambda l: l.product_id == dhl_product)
        if existing_line:
            # Update the existing line (assuming 1 unit)
            existing_line.write({
                'price_unit': total_dhl_cost,
                'product_qty': 1.0,
            })
            _logger.info("Updated existing DHL PO line for PO %s", self.name)
        else:
            # Create a new line
            self.write({
                'order_line': [(0, 0, {
                    'product_id': dhl_product.id,
                    'product_qty': 1.0,
                    'price_unit': total_dhl_cost,
                    'name': _("DHL Shipping & Duties: %s") % dhl_product.display_name,
                    'date_planned': self.date_planned or fields.Datetime.now(),
                })]
            })
            _logger.info("Created new DHL PO line for PO %s", self.name)

    @api.onchange('partner_id', 'picking_type_id', 'dest_address_id', 'incoterm_id', 'order_line', 'company_id')
    def _onchange_dhl_trigger(self):
        if not self.is_estimate_frozen:
            # Safely set DHL account if company changed
            if self.company_id and not self.dhl_account_number:
                 self.dhl_account_number = getattr(self.company_id, 'dhl_account_number', '')
                 
            if self.partner_id and (self.dest_address_id or self.picking_type_id.warehouse_id.partner_id):
                try:
                    # We only auto-call if we have the basics: vendor, destination, and some weight
                    if self.total_weight > 0:
                        self.action_get_dhl_quote()
                        self.action_get_duty_rate()
                except Exception:
                    # Avoid blocking UI on API errors during onchange
                    pass


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    is_dhl = fields.Boolean(
        related='product_id.is_dhl',
        store=True, copy=False
    )
    is_generated = fields.Boolean(string="Is Generated", related='product_id.is_generated', store=True)
