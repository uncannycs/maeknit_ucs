from odoo import models
from datetime import timedelta


LUNCH_DEDUCTION = timedelta(minutes=30)
MIN_SHIFT_HOURS = 6
SEVAN = 'Sevan Altan'


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    def write(self, vals):
        result = super().write(vals)

        if 'check_out' not in vals:
            return result

        for record in self:
            if not record.check_in or not record.check_out:
                continue

            # Only apply to Sevan
            if SEVAN.lower() not in record.employee_id.name.lower():
                continue

            # Only apply deduction if this is a single clock-in/clock-out for the day
            # (i.e., employee did NOT manually punch a lunch break)
            check_in_date = record.check_in.date()
            same_day_count = self.env['hr.attendance'].search_count([
                ('employee_id', '=', record.employee_id.id),
                ('check_in', '>=', str(check_in_date)),
                ('check_in', '<', str(check_in_date + timedelta(days=1))),
            ])

            if same_day_count > 1:
                # Employee already has multiple records — manual lunch punch exists, skip
                continue

            raw_duration = record.check_out - record.check_in
            if raw_duration < timedelta(hours=MIN_SHIFT_HOURS):
                continue

            # Calculate the midpoint of the shift, then place lunch 15 min either side
            midpoint = record.check_in + raw_duration / 2
            lunch_start = midpoint - timedelta(minutes=15)
            lunch_end = midpoint + timedelta(minutes=15)

            # Shrink the main shift: check_out becomes lunch_start, then create lunch record
            # After lunch, a second attendance record covers lunch_end -> original check_out
            original_check_out = record.check_out

            # Shorten this record to end at lunch start
            super(HrAttendance, record).write({'check_out': lunch_start})

            # Create the lunch break record (punch in/out for the 30-min break)
            self.env['hr.attendance'].sudo().create({
                'employee_id': record.employee_id.id,
                'check_in': lunch_start,
                'check_out': lunch_end,
                'reason': 'Lunch break',
            })

            # Create the afternoon record from lunch end to original check_out
            self.env['hr.attendance'].sudo().create({
                'employee_id': record.employee_id.id,
                'check_in': lunch_end,
                'check_out': original_check_out,
            })

        return result
