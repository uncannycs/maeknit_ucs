from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    contact_type = fields.Selection([
        ('individual', 'Individual'),
        ('student', 'Student'),
        ('buyer', 'Buyer'),
        ('brand', 'Brand'),
        ('vendor', 'Vendor'),
        ('factory', 'Factory'),
        ('agency', 'Agency'),
        ('university', 'University'),
        ('company', 'Company (not listed)'),
    ], string="Contact Type", required=True)

    def _normalize_email(self, email):
        return email.strip().lower() if email else False

    @api.onchange('contact_type')
    def _onchange_contact_type(self):
        self.company_type = 'company' if self.contact_type in ['factory', 'brand', 'vendor', 'agency', 'university', 'company'] else 'person'
        self.supplier_rank = 1 if self.contact_type in ['vendor', 'factory'] else 0


    @api.model_create_multi
    def create(self, vals_list):
        result = self.env[self._name].browse()
        for vals in vals_list:
            if not vals.get('contact_type'):
                vals['contact_type'] = 'individual'

            vals['company_type'] = 'company' if vals['contact_type'] in [
                'factory', 'brand', 'vendor', 'agency', 'university', 'company'
            ] else 'person'
            vals['supplier_rank'] = 1 if vals['contact_type'] in ['vendor', 'factory'] else 0

            # Check for duplicate email
            email_norm = self._normalize_email(vals.get('email'))
            if email_norm:
                existing = self.search([('email', 'ilike', email_norm)], limit=1)
                if existing:
                    # Update existing record with any provided values
                    update_vals = {
                        k: v for k, v in vals.items()
                        if v not in [False, None, '']  # don’t overwrite with empty values
                        and k not in ['email']         # email is already the match key
                    }
                    if update_vals:
                        existing.write(update_vals)
                    result |= existing
                    continue

            # If not duplicate, create new
            new_partner = super(ResPartner, self).create([vals])
            result |= new_partner
        return result



    def write(self, vals):
        if 'contact_type' in vals:
            if not vals['contact_type']:
                raise ValidationError(_("Contact Type cannot be empty."))
            vals.setdefault('company_type',
                'company' if vals['contact_type'] in [
                    'factory', 'brand', 'vendor', 'agency', 'university', 'company'
                ] else 'person')
            vals['supplier_rank'] = 1 if vals['contact_type'] in ['vendor', 'factory'] else 0
        return super().write(vals)


    def _set_default_contact_type(self):
        for partner in self:
            if partner.company_type == 'company':
                partner.contact_type = 'vendor'
                partner.supplier_rank = 1
            else:
                partner.contact_type = 'individual'
                partner.supplier_rank = 0