/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { FormRenderer } from "@web/views/form/form_renderer";
import { useEffect, useRef } from "@odoo/owl";

patch(FormRenderer.prototype, {
    setup() {
        super.setup();
        const rootRef = useRef("compiled_view_root");
        useEffect(
            () => {
                const el = rootRef.el;
                if (!el || this.props.record.resModel !== "mrp.production") return;
                const isUk = this.props.record.data.is_uk_company;
                el.classList.toggle("o_mrp_uk_company", !!isUk);
            },
            () => [this.props.record.resModel, this.props.record.data.is_uk_company]
        );
    },
});
