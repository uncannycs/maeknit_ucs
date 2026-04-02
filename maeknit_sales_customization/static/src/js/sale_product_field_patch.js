/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";
import { x2ManyCommands } from "@web/core/orm_service";
import { SaleOrderLineProductField } from "@sale/js/sale_product_field";

/**
 * Patch SaleOrderLineProductField to replace the product configurator dialog
 * with a simple variant picker that also includes the base "no variant" option.
 */
patch(SaleOrderLineProductField.prototype, {
    async _openProductConfigurator(edit = false) {
        // When editing an existing line, use the standard configurator dialog
        if (edit) {
            return super._openProductConfigurator(edit);
        }

        const saleOrderRecord = this.props.record.model.root;
        const saleOrderLine = this.props.record.data;
        const productTemplateId = saleOrderLine.product_template_id[0];

        // Fetch all active variants for this template, including the base (no-attribute) variant
        let variants;
        try {
            variants = await this.orm.searchRead(
                'product.product',
                [['product_tmpl_id', '=', productTemplateId], ['active', '=', true]],
                ['id', 'display_name', 'product_template_attribute_value_ids'],
                { order: 'id asc' }
            );
        } catch (_e) {
            return super._openProductConfigurator(edit);
        }

        if (!variants || variants.length === 0) {
            return super._openProductConfigurator(edit);
        }

        // Only one variant — apply directly without any dialog
        if (variants.length === 1) {
            await this._applyVariant(variants[0], saleOrderLine, saleOrderRecord);
            return;
        }

        // Multiple variants — show simple picker (includes the base "no variant" row)
        this.dialog.add(MaeknitVariantPickerDialog, {
            variants: variants,
            save: async (variant) => {
                await this._applyVariant(variant, saleOrderLine, saleOrderRecord);
            },
            discard: () => {
                saleOrderRecord.data.order_line.delete(this.props.record);
            },
        });
    },

    async _applyVariant(variant, saleOrderLine, saleOrderRecord) {
        await this.props.record._update({
            product_id: [variant.id, variant.display_name],
            product_uom_qty: saleOrderLine.product_uom_qty || 1,
            product_no_variant_attribute_value_ids: [x2ManyCommands.set([])],
            product_custom_attribute_value_ids: [x2ManyCommands.set([])],
        });
        this._onProductUpdate();
        saleOrderRecord.data.order_line.leaveEditMode();
    },
});


class MaeknitVariantPickerDialog extends Component {
    static template = "maeknit_sales_customization.VariantPickerDialog";
    static components = { Dialog };
    static props = {
        variants: Array,
        save: Function,
        discard: Function,
        close: Function,
    };

    setup() {
        this.state = useState({ selectedId: this.props.variants[0].id });
    }

    get selectedVariant() {
        return this.props.variants.find(v => v.id === this.state.selectedId);
    }

    onSelect(id) {
        this.state.selectedId = id;
    }

    onConfirm() {
        this.props.save(this.selectedVariant);
        this.props.close();
    }

    onDiscard() {
        this.props.discard();
        this.props.close();
    }
}
