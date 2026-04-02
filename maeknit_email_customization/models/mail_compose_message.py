from odoo import models, api
from markupsafe import Markup
import logging
import re

class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    def _apply_font_styling(self, body):
        """Apply consistent sans-serif styling and preserve line breaks properly."""
        if not body:
            return body

        body_str = str(body) if isinstance(body, Markup) else body

        # Normalize raw text or hybrid body (HTML fragments without <p> or <div>)
        is_html = bool(re.search(r'<(p|div|br|span|table|ul|ol|li|strong|em|a|b|i)\b', body_str, re.I))

        if not is_html:
            # Treat as plain text — escape HTML then preserve newlines as <br>
            safe = escape(body_str)
            safe = safe.replace("\r\n", "\n").replace("\n", "<br/>")
            styled = (
                '<div style="font-family: sans-serif; font-size: 13px; '
                'line-height: 1.5; white-space: normal;">'
                f'{safe}</div>'
            )
            return Markup(styled)

        # Handle HTML that may contain <br> tags but no top-level wrapper
        if not re.search(r'<(html|body|p|div)\b', body_str, re.I):
            body_str = f'<div>{body_str}</div>'

        # Inject font styling only if not already present
        if 'font-family: sans-serif' not in body_str:
            body_str = re.sub(
                r'<(div|p)([^>]*)>',
                r'<\1\2 style="font-family: sans-serif; font-size: 13px; line-height: 1.5;">',
                body_str,
                count=1,
            )

        return Markup(body_str)

    @api.onchange('body')
    def _onchange_body(self):
        """Apply sans-serif font styling when the body is changed in the composer"""
        if self.body:
            self.body = self._apply_font_styling(self.body)
    
    @api.onchange('subject')
    def _onchange_subject(self):
        """Log when subject changes in the composer"""
        logging.info("Composer subject changed to: %s", self.subject)
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to ensure subject is properly set"""
        for vals in vals_list:
            if vals.get('model') and vals.get('res_id') and not vals.get('subject'):
                # Try to get the most recent subject from the thread
                recent_message = self.env['mail.message'].search([
                    ('model', '=', vals['model']),
                    ('res_id', '=', vals['res_id']),
                    ('subject', '!=', False),
                ], order='id desc', limit=1)
                
                if recent_message and recent_message.subject:
                    vals['subject'] = recent_message.subject
                    logging.info("Setting composer subject to most recent: %s", vals['subject'])

            # Apply styling to body if present
            if vals.get('body'):
                vals['body'] = self._apply_font_styling(vals['body'])

        return super(MailComposeMessage, self).create(vals_list)

    
    def send_mail(self, auto_commit=False):
        """Override to apply sans-serif font styling before sending the email"""
        # Log all composer values for debugging
        for composer in self:
            logging.info("Mail composer values before send: %s", composer.read(['subject', 'body', 'model', 'res_id', 'template_id']))
            logging.info("Composer subject before send: %s", composer.subject)
            
            # If no subject is provided, try to get the most recent subject from the thread
            if not composer.subject and composer.model and composer.res_id:
                recent_message = self.env['mail.message'].search([
                    ('model', '=', composer.model),
                    ('res_id', '=', composer.res_id),
                    ('subject', '!=', False),
                ], order='id desc', limit=1)
                
                if recent_message and recent_message.subject:
                    composer.subject = recent_message.subject
                    logging.info("Using most recent subject for continuity: %s", composer.subject)
            
            # Apply styling to the body before sending
            if composer.body:
                composer.body = self._apply_font_styling(composer.body)
                logging.info("Applied sans-serif font styling to mail composer body")
        
        result = super(MailComposeMessage, self).send_mail(auto_commit=auto_commit)
        logging.info("Mail composer send_mail completed with result: %s", result)
        return result
