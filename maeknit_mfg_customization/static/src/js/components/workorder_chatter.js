/** @odoo-module */

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Chatter } from "@mail/chatter/web_portal/chatter";

class WorkorderChatterWidget extends Component {
    static template = "maeknit_mfg_customization.WorkorderChatterWidget";
    static components = { Chatter };
    static props = { ...standardFieldProps };

    get workorderId() {
        const value = this.props.record.data[this.props.name];
        return value ? value[0] : false;
    }
}

registry.category("fields").add("workorder_chatter", {
    component: WorkorderChatterWidget,
    supportedTypes: ["many2one"],
});
