from . import models
from . import controllers


def _ensure_shipstation_carrier_active(env):
    """Ensure the ShipStation delivery carrier is always active after install/upgrade."""
    carriers = env['delivery.carrier'].with_context(active_test=False).search([
        ('delivery_type', '=', 'shipstation'),
    ])
    if carriers:
        carriers.filtered(lambda c: not c.active).write({'active': True})