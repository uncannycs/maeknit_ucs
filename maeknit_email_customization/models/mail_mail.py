from odoo import models, api, fields
import logging
import re
from markupsafe import Markup

# Log when the module is loaded
logging.info("MailMail module loaded - Subject modification module ready")

class MailMail(models.Model):
    _inherit = 'mail.mail'
    
    # Use _register_hook instead of __init__ for initialization logging
    @api.model
    def _register_hook(self):
        return super(MailMail, self)._register_hook()
    
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

    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to modify the subject of outgoing emails"""        
        for vals in vals_list:
            # Detailed logging of all values
            logging.info("Mail create vals: %s", vals)
            
            # Apply font styling to the HTML body
            if vals.get('body_html'):
                vals['body_html'] = self._apply_font_styling(vals['body_html'])
                logging.info("Applied font styling to email HTML body")
            
            # Check if this is an email created from a message            
            if vals.get('mail_message_id'):
                logging.info("Found mail_message_id: %s", vals.get('mail_message_id'))
                
                message = self.env['mail.message'].browse(vals['mail_message_id'])
                logging.info("Related message model: %s, res_id: %s", message.model, message.res_id)
                
                if message.model and message.res_id:
                    # Find all previous messages in this thread
                    previous_messages = self.env['mail.message'].search([
                        ('model', '=', message.model),
                        ('res_id', '=', message.res_id),
                        ('message_type', 'in', ['comment', 'email']),
                        ('id', '!=', message.id),
                    ], order='id desc')
                    
                    # Find the most recent message with a subject
                    recent_messages_with_subject = self.env['mail.message'].search([
                        ('model', '=', message.model),
                        ('res_id', '=', message.res_id),
                        ('subject', '!=', False),
                        ('id', '!=', message.id),
                    ], order='id desc', limit=1)
                    
                    logging.info("Previous messages count: %s", len(previous_messages))
                    logging.info("Most recent message with subject: %s", recent_messages_with_subject)
                    
                    # Check if this is from expanded view (has explicit subject)
                    is_from_expanded = message.subject and message.subject != vals.get('subject', '')
                    logging.info("Is from expanded view: %s, message subject: %s", is_from_expanded, message.subject)
                    
                    # Check if this is the first message in the thread
                    is_first_message = len(previous_messages) == 0
                    logging.info("Is first message: %s", is_first_message)
                    
                    # Subject handling logic:
                    # 1. If from expanded view with explicit subject, use that
                    # 2. If continuing a thread, use the most recent subject
                    # 3. If it's the first message, apply the MAEKNIT INC prefix
                    
                    if message.subject and is_from_expanded:
                        # If from expanded view with explicit subject, use that
                        logging.info("Using explicit subject from expanded view: %s", message.subject)
                        vals['subject'] = message.subject
                    elif recent_messages_with_subject and not is_first_message:
                        # If continuing a thread, use the most recent subject
                        logging.info("Using most recent thread subject: %s", recent_messages_with_subject.subject)
                        vals['subject'] = recent_messages_with_subject.subject
                    else:
                        # If it's the first message or no previous subject, apply MAEKNIT INC prefix
                        record = self.env[message.model].browse(message.res_id)
                        if record.exists():
                            # Get the base subject (either from vals or record name)
                            base_subject = vals.get('subject') or record.display_name
                            logging.info("Base subject for first message: %s", base_subject)
                            
                            # Format the subject with MAEKNIT INC prefix
                            if message.model == 'res.partner':
                                subject = f"Message from MAEKNIT INC"
                            elif message.model == 'crm.lead':
                                # Customize based on opportunity/lead type
                                subject = f"MAEKNIT INC – {base_subject}"
                            else:
                                model_name = self.env['ir.model']._get(message.model).name
                                subject = f"MAEKNIT INC {model_name}: {base_subject}"
                                
                            logging.info("Setting formatted email subject for first message: %s", subject)
                            vals['subject'] = subject
                    
                    # Ensure we have the correct references for threading
                    if previous_messages and vals.get('references'):
                        # Build references string with all message IDs to maintain threading
                        refs = []
                        for msg in previous_messages:
                            msg_id = msg.message_id or f'<{msg.id}-openerp-{msg.res_id}-{msg.model}@{self.env["ir.config_parameter"].sudo().get_param("web.base.url", "localhost")}>'
                            if msg_id and msg_id not in refs:
                                refs.append(msg_id)
                        
                        if refs:
                            vals['references'] = ' '.join(refs)
                            logging.info("Updated references for threading: %s", vals['references'])
                
                logging.info("Final subject being used: %s", vals.get('subject'))
        
        mails = super(MailMail, self).create(vals_list)
        # Log the final created mails
        for mail in mails:
            logging.info("Created mail ID: %s with subject: %s", mail.id, mail.subject)
        return mails
