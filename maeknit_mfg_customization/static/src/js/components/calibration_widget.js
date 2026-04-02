"use client";

/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class CalibrationWidget extends Component {
  static template = "maeknit_mfg_customization.CalibrationWidget";
  static props = {
    ...standardFieldProps,
    hideSwatchSelection: { type: Boolean, optional: true },
  };

  setup() {
    // Hooks must be called at the top level
    this.orm = useService("orm");
    this.notification = useService("notification");
    this.action = useService("action");

    this.state = useState({
      hasPreExistingSwatch: false,
      calibrationSwatchId: null,
      calibrationSwatchName: "",

      // Global measurement unit
      measurementUnit: "inches", // Global unit: "inches" or "cm"

      // Body section
      bodySwatchSpecsX: 0,
      bodySwatchSpecsY: 0,
      bodyMeasurementX: 0,
      bodyMeasurementY: 0,
      bodyCalibrationX: 0,
      bodyCalibrationY: 0,

      // Cuff section
      cuffSwatchSpecsX: 0,
      cuffSwatchSpecsY: 0,
      cuffMeasurementX: 0,
      cuffMeasurementY: 0,
      cuffCalibrationX: 0,
      cuffCalibrationY: 0,

      widthImageAttachmentId: null,
      heightImageAttachmentId: null,
      widthImage2AttachmentId: null,
      heightImage2AttachmentId: null,

      // Images for display (loaded from attachments)
      widthImage: null,
      heightImage: null,
      widthImage2: null,
      heightImage2: null,

      availableSwatches: [],

      isDirty: false,

      zoomLevels: {
        width: 1.0,
        height: 1.0,
        width2: 1.0,
        height2: 1.0,
      },
    });

    this.dragState = {
      isDragging: false,
      startX: 0,
      startY: 0,
      scrollLeft: 0,
      scrollTop: 0,
      container: null,
      imageType: null,
    };

    // Bind methods
    this.onPreExistingChange = this.onPreExistingChange.bind(this);
    this.onSwatchChange = this.onSwatchChange.bind(this);
    this.generateCalibrationSwatch = this.generateCalibrationSwatch.bind(this);
    this.toggleUnit = this.toggleUnit.bind(this);
    this.updateField = this.updateField.bind(this);
    this.calculateCalibrationValues =
      this.calculateCalibrationValues.bind(this);
    this.handleImageUpload = this.handleImageUpload.bind(this);
    this.triggerFileInput = this.triggerFileInput.bind(this);
    this.handleDrop = this.handleDrop.bind(this);
    this.notifyFormChange = this.notifyFormChange.bind(this);
    this.getAvailableSwatches = this.getAvailableSwatches.bind(this);
    this.loadAvailableSwatches = this.loadAvailableSwatches.bind(this);

    this.adjustZoom = this.adjustZoom.bind(this);
    this.resetZoom = this.resetZoom.bind(this);
    this.fitToContainer = this.fitToContainer.bind(this);
    this.handleWheel = this.handleWheel.bind(this);
    this.handleMouseDown = this.handleMouseDown.bind(this);
    this.handleMouseMove = this.handleMouseMove.bind(this);
    this.handleMouseUp = this.handleMouseUp.bind(this);

    // Hide Pre-existing/Generate UI for Swatch Service MOs (they ARE the swatch)
    this.hideSwatchSelection = this.props.record.data?.is_swatch_bom
      || this.props.record.data?.is_swatch_mo;

    let parsedValue = null;

    const rawValue = this.props.record?.data?.[this.props.name];
    if (rawValue) {
      if (typeof rawValue === "string" && rawValue.trim() !== "") {
        try {
          parsedValue = JSON.parse(rawValue);
        } catch (e) {
          console.error(
            " Error parsing calibration data:",
            e,
            "Raw value:",
            rawValue
          );
        }
      } else if (typeof rawValue === "object" && rawValue !== null) {
        parsedValue = rawValue;
      }
    }

    // After assigning parsedValue into this.state
    if (parsedValue && typeof parsedValue === "object") {
      const validFields = Object.keys(this.state);

      // Normalize images so they always render correctly
      const normalizeImage = (img) => {
        if (!img) return null;
        if (img.startsWith("data:image")) return img;
        return "data:image/png;base64," + img;
      };

      Object.keys(parsedValue).forEach((key) => {
        if (validFields.includes(key)) {
          if (
            key === "widthImage" ||
            key === "heightImage" ||
            key === "widthImage2" ||
            key === "heightImage2"
          ) {
            this.state[key] = normalizeImage(parsedValue[key]);
          } else {
            this.state[key] = parsedValue[key];
          }
        }
      });
      this.calculateCalibrationValues();
    }

    console.log(
      "props data is swatch bom",
      this.props.record.data?.is_swatch_bom
    );
    console.log("record", this.props.record);

    this.loadAvailableSwatches();

    this.loadImagesFromAttachments();
  }

  onPreExistingChange(event) {
    this.state.hasPreExistingSwatch = event.target.value === "yes";
    this.notifyFormChange();
  }

  resetCalibrationFields() {
    // swatch selection metadata
    this.state.calibrationSwatchName = "";

    // body
    this.state.bodySwatchSpecsX = 0;
    this.state.bodySwatchSpecsY = 0;
    this.state.bodyMeasurementX = 0;
    this.state.bodyMeasurementY = 0;
    this.state.bodyCalibrationX = 0;
    this.state.bodyCalibrationY = 0;

    // cuff
    this.state.cuffSwatchSpecsX = 0;
    this.state.cuffSwatchSpecsY = 0;
    this.state.cuffMeasurementX = 0;
    this.state.cuffMeasurementY = 0;
    this.state.cuffCalibrationX = 0;
    this.state.cuffCalibrationY = 0;

    this.state.widthImageAttachmentId = null;
    this.state.heightImageAttachmentId = null;
    this.state.widthImage2AttachmentId = null;
    this.state.heightImage2AttachmentId = null;
    this.state.widthImage = null;
    this.state.heightImage = null;
    this.state.widthImage2 = null;
    this.state.heightImage2 = null;

    // unit default
    this.state.measurementUnit = "inches";
  }

  async onSwatchChange(event) {
    const swatchId = Number.parseInt(event.target.value);
    if (!swatchId) return;

    // select swatch and clear UI first
    this.state.calibrationSwatchId = swatchId;
    this.resetCalibrationFields();
    this.calculateCalibrationValues(); // optional; keeps derived fields consistent

    try {
      const swatch = await this.orm.read(
        "mrp.production",
        [swatchId],
        ["name"]
      );
      if (swatch?.length)
        this.state.calibrationSwatchName = swatch[0].name;

      let calibrationData = await this.orm.call(
        "mrp.production",
        "get_calibration_data_for_swatch",
        [swatchId]
      );

      if (typeof calibrationData === "string") {
        try {
          calibrationData = JSON.parse(calibrationData);
        } catch (err) {
          console.error("Invalid JSON returned from backend:", calibrationData);
          this.notifyFormChange();
          return;
        }
      }

      // if nothing useful returned, keep it empty
      if (!calibrationData || typeof calibrationData !== "object") {
        this.notifyFormChange();
        return;
      }

      const norm = (img) =>
        !img
          ? null
          : img.startsWith("data:image")
          ? img
          : "data:image/png;base64," + img;

      this.state.bodySwatchSpecsX = calibrationData.bodySwatchSpecsX ?? 0;
      this.state.bodySwatchSpecsY = calibrationData.bodySwatchSpecsY ?? 0;
      this.state.bodyMeasurementX = calibrationData.bodyMeasurementX ?? 0;
      this.state.bodyMeasurementY = calibrationData.bodyMeasurementY ?? 0;

      this.state.cuffSwatchSpecsX = calibrationData.cuffSwatchSpecsX ?? 0;
      this.state.cuffSwatchSpecsY = calibrationData.cuffSwatchSpecsY ?? 0;
      this.state.cuffMeasurementX = calibrationData.cuffMeasurementX ?? 0;
      this.state.cuffMeasurementY = calibrationData.cuffMeasurementY ?? 0;

      this.state.measurementUnit = calibrationData.measurementUnit ?? "inches";

      this.state.widthImageAttachmentId =
        calibrationData.widthImageAttachmentId ?? null;
      this.state.heightImageAttachmentId =
        calibrationData.heightImageAttachmentId ?? null;
      this.state.widthImage2AttachmentId =
        calibrationData.widthImage2AttachmentId ?? null;
      this.state.heightImage2AttachmentId =
        calibrationData.heightImage2AttachmentId ?? null;

      // Load images from attachments
      await this.loadImagesFromAttachments();

      this.calculateCalibrationValues();
    } catch (e) {
      console.error(e);
      // keep empty if error
    }

    this.notifyFormChange();
  }

  async generateCalibrationSwatch() {
    if (!this.props.record?.resId) {
      this.notification.add("Please save the Manufacturing Order first", {
        type: "warning",
      });
      return;
    }

    try {
      let result = "";
      try {
        result = await this.orm.call(
          "mrp.production",
          "action_generate_calibration_swatch",
          [[this.props.record.resId]]
        );
      } catch (error) {
        console.log("ERROR", error);
      }

      console.log(" Result from backend:", result);

      if (result && result.type === "ir.actions.act_window") {
        console.log(" Executing action to navigate to new MO:", result.res_id);

        await this.loadAvailableSwatches();

        await this.action.doAction(result);
        console.log(" Navigation completed");
      } else {
        console.error(" Unexpected result format:", result);
        this.notification.add(
          "Calibration swatch created but navigation failed",
          {
            type: "warning",
          }
        );
      }
    } catch (error) {
      console.error(" Error generating calibration swatch:", error);
      const errorMessage =
        error.message || error.data?.message || "Unknown error occurred";
      this.notification.add(
        `Error generating calibration swatch: ${errorMessage}`,
        {
          type: "danger",
        }
      );
    }
  }

  updateField(field, value) {
    this.state[field] = value;
    this.calculateCalibrationValues();
    this.notifyFormChange();
  }

  calculateCalibrationValues() {
    // Body Calibration Y = Y needles from swatch specs / measurement Y axis
    if (this.state.bodyMeasurementY && this.state.bodyMeasurementY !== 0) {
      this.state.bodyCalibrationY = (
        this.state.bodySwatchSpecsY / this.state.bodyMeasurementY
      ).toFixed(3);
    } else {
      this.state.bodyCalibrationY = 0;
    }

    // Body Calibration X = X stitches from swatch specs / measurement X axis
    if (this.state.bodyMeasurementX && this.state.bodyMeasurementX !== 0) {
      this.state.bodyCalibrationX = (
        this.state.bodySwatchSpecsX / this.state.bodyMeasurementX
      ).toFixed(3);
    } else {
      this.state.bodyCalibrationX = 0;
    }

    // Cuff Calibration Y = Y needles from swatch specs / measurement Y axis
    if (this.state.cuffMeasurementY && this.state.cuffMeasurementY !== 0) {
      this.state.cuffCalibrationY = (
        this.state.cuffSwatchSpecsY / this.state.cuffMeasurementY
      ).toFixed(3);
    } else {
      this.state.cuffCalibrationY = 0;
    }

    // Cuff Calibration X = X stitches from swatch specs / measurement X axis
    if (this.state.cuffMeasurementX && this.state.cuffMeasurementX !== 0) {
      this.state.cuffCalibrationX = (
        this.state.cuffSwatchSpecsX / this.state.cuffMeasurementX
      ).toFixed(3);
    } else {
      this.state.cuffCalibrationX = 0;
    }
    this.notifyFormChange();
  }

  async handleImageUpload(event, imageType) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (e) => {
      const base64Data = e.target.result.split(",")[1]; // Remove data:image/png;base64, prefix

      try {
        const resModel = this.props.record?.resModel; // 'mrp.production', 'mrp.workorder', or 'maeknit.bom.request'
        const resId = this.props.record?.resId;

        const attachment = await this.orm.create("ir.attachment", [
          {
            name: `${imageType}_${Date.now()}.png`,
            type: "binary",
            datas: base64Data,
            res_model: resModel,
            res_id: resId,
            res_field:
              imageType === "width"
                ? "width_image"
                : imageType === "height"
                ? "height_image"
                : imageType === "width2"
                ? "width_image_2"
                : "height_image_2",
            mimetype: "image/png",
          },
        ]);

        if (imageType === "width") {
          this.state.widthImageAttachmentId = attachment;
          this.state.widthImage = e.target.result;
        } else if (imageType === "height") {
          this.state.heightImageAttachmentId = attachment;
          this.state.heightImage = e.target.result;
        } else if (imageType === "width2") {
          this.state.widthImage2AttachmentId = attachment;
          this.state.widthImage2 = e.target.result;
        } else if (imageType === "height2") {
          this.state.heightImage2AttachmentId = attachment;
          this.state.heightImage2 = e.target.result;
        }

        this.notifyFormChange();
      } catch (error) {
        console.error("Error creating attachment:", error);
        this.notification.add("Failed to upload image", { type: "danger" });
      }
    };
    reader.readAsDataURL(file);
  }

  handleDrop(event, imageType) {
    event.preventDefault();
    event.stopPropagation();

    const files = event.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];
      if (file.type.startsWith("image/")) {
        const reader = new FileReader();
        reader.onload = async (e) => {
          const base64Data = e.target.result.split(",")[1];

          try {
            const resModel = this.props.record?.resModel;
            const resId = this.props.record?.resId;

            const attachment = await this.orm.create("ir.attachment", [
              {
                name: `${imageType}_${Date.now()}.png`,
                type: "binary",
                datas: base64Data,
                res_model: resModel,
                res_id: resId,
                res_field:
                  imageType === "width"
                    ? "width_image"
                    : imageType === "height"
                    ? "height_image"
                    : imageType === "width2"
                    ? "width_image_2"
                    : "height_image_2",
                mimetype: "image/png",
              },
            ]);
            
            if (imageType === "width") {
              this.state.widthImageAttachmentId = attachment;
              this.state.widthImage = e.target.result;
            } else if (imageType === "height") {
              this.state.heightImageAttachmentId = attachment;
              this.state.heightImage = e.target.result;
            } else if (imageType === "width2") {
              this.state.widthImage2AttachmentId = attachment;
              this.state.widthImage2 = e.target.result;
            } else if (imageType === "height2") {
              this.state.heightImage2AttachmentId = attachment;
              this.state.heightImage2 = e.target.result;
            }

            this.notifyFormChange();
          } catch (error) {
            console.error("Error creating attachment:", error);
            this.notification.add("Failed to upload image", { type: "danger" });
          }
        };
        reader.readAsDataURL(file);
      }
    }
  }

  triggerFileInput(imageType) {
    const fileInput = this.__owl__.refs[`${imageType}FileInput`];
    if (fileInput) {
      fileInput.click();
    }
  }

  getCalibrationAttachmentId(imageType) {
    switch (imageType) {
      case "width":
        return this.state.widthImageAttachmentId;
      case "height":
        return this.state.heightImageAttachmentId;
      case "width2":
        return this.state.widthImage2AttachmentId;
      case "height2":
        return this.state.heightImage2AttachmentId;
      default:
        return null;
    }
  }

  getCalibrationDownloadUrl(imageType) {
    const attachmentId = this.getCalibrationAttachmentId(imageType);
    if (!attachmentId) {
      return null;
    }
    return `/web/content/${attachmentId}?download=1`;
  }

  notifyFormChange() {
    try {
      const fieldData = { ...this.state };
      delete fieldData.isDirty;
      delete fieldData.availableSwatches;

      delete fieldData.widthImage;
      delete fieldData.heightImage;
      delete fieldData.widthImage2;
      delete fieldData.heightImage2;
      delete fieldData.zoomLevels;

      const jsonString = JSON.stringify(fieldData);
      console.log("Serialized JSON string:", jsonString);

      // The widget may be bound to calibration_data_with_images for display, but we must
      // persist changes to the actual stored field to ensure data persists after reload
      const changes = { calibration_data: jsonString };
      console.log("Changes object:", changes);
      console.log("Calling props.record.update with changes");

      this.props.record.update(changes);

      console.log("props.record.update called successfully");
      console.log("Record isDirty:", this.props.record.isDirty);
      console.log("Record dirty fields:", this.props.record.dirtyFields);

      console.log("Triggering auto-save...");
      this.props.record.save();
      console.log("Auto-save triggered successfully");

      this.state.isDirty = true;
      console.log("notifyFormChange completed");
    } catch (error) {
      console.error("Error notifying form change:", error);
      console.error("Error stack:", error.stack);
    }
  }

  async getAvailableSwatches() {
    try {
      const rec = this.props.record;
      const model = rec?.resModel; // "mrp.production" or "mrp.workorder"
  
      let partnerId = null;
  
      if (model === "mrp.production") {
        partnerId = rec?.data?.partner_id?.[0];
      } else if (model === "mrp.workorder") {
        const moId = rec?.data?.production_id?.[0];
        if (moId) {
          const [mo] = await this.orm.read(
            "mrp.production",
            [moId],
            ["partner_id"]
          );
          partnerId = mo?.partner_id?.[0];
        }
      } else {
        // fallback if you reuse widget elsewhere
        partnerId = rec?.data?.partner_id?.[0] || null;
        if (!partnerId) {
          const moId = rec?.data?.production_id?.[0];
          if (moId) {
            const [mo] = await this.orm.read(
              "mrp.production",
              [moId],
              ["partner_id"]
            );
            partnerId = mo?.partner_id?.[0];
          }
        }
      }
  
      if (!partnerId) {
        console.log("No client found; returning empty list");
        return [];
      }
  
      const swatches = await this.orm.call(
        "mrp.production",
        "get_calibration_swatches_for_client",
        [partnerId]
      );
  
      return swatches || [];
    } catch (error) {
      console.error("Error fetching available swatches:", error);
      return [];
    }
  }


  async loadAvailableSwatches() {
    try {
      const swatches = await this.getAvailableSwatches();
      this.state.availableSwatches = swatches;
      console.log(" Loaded available swatches:", swatches);
    } catch (error) {
      console.error(" Error loading available swatches:", error);
      this.state.availableSwatches = [];
    }
  }

  toggleUnit() {
    this.state.measurementUnit =
      this.state.measurementUnit === "inches" ? "cm" : "inches";
    this.notifyFormChange();
  }

  adjustZoom(imageType, delta) {
    const newZoom = Math.min(
      5,
      Math.max(0.5, this.state.zoomLevels[imageType] + delta)
    );
    this.state.zoomLevels[imageType] = newZoom;

    const wrapper = document.querySelector(`.image-wrapper-${imageType}`);
    if (wrapper) {
      wrapper.style.transform = `scale(${newZoom})`;
    }
  }

  resetZoom(imageType) {
    this.state.zoomLevels[imageType] = 1.0;
    const wrapper = document.querySelector(`.image-wrapper-${imageType}`);
    const container = document.querySelector(`.zoom-container-${imageType}`);

    if (wrapper) {
      wrapper.style.transform = "scale(1)";
      wrapper.style.left = "0px";
      wrapper.style.top = "0px";
    }

    if (container) {
      container.scrollTop = 0;
      container.scrollLeft = 0;
    }
  }

  fitToContainer(imageType) {
    this.state.zoomLevels[imageType] = 1.0;
    const wrapper = document.querySelector(`.image-wrapper-${imageType}`);
    const container = document.querySelector(`.zoom-container-${imageType}`);

    if (wrapper) {
      wrapper.style.transform = "scale(1)";
      wrapper.style.left = "0px";
      wrapper.style.top = "0px";
    }

    if (container) {
      container.scrollTop = 0;
      container.scrollLeft = 0;
    }
  }

  handleWheel(event, imageType) {
    event.preventDefault();
    const delta = event.deltaY < 0 ? 0.1 : -0.1;
    this.adjustZoom(imageType, delta);
  }

  handleMouseDown(event, imageType) {
    // Only handle left mouse button
    if (event.button !== 0) return;

    const wrapper = document.querySelector(`.image-wrapper-${imageType}`);
    if (!wrapper) return;

    this.dragState.isDragging = true;
    this.dragState.imageType = imageType;
    this.dragState.startX = event.clientX;
    this.dragState.startY = event.clientY;

    const currentLeft = Number.parseFloat(wrapper.style.left || "0");
    const currentTop = Number.parseFloat(wrapper.style.top || "0");
    this.dragState.scrollLeft = currentLeft;
    this.dragState.scrollTop = currentTop;

    document.addEventListener("mousemove", this.handleMouseMove);
    document.addEventListener("mouseup", this.handleMouseUp);

    event.preventDefault();
  }

  handleMouseMove(event) {
    if (!this.dragState.isDragging) return;

    const wrapper = document.querySelector(
      `.image-wrapper-${this.dragState.imageType}`
    );
    if (!wrapper) return;

    const deltaX = event.clientX - this.dragState.startX;
    const deltaY = event.clientY - this.dragState.startY;

    wrapper.style.left = `${this.dragState.scrollLeft + deltaX}px`;
    wrapper.style.top = `${this.dragState.scrollTop + deltaY}px`;
  }

  handleMouseUp() {
    this.dragState.isDragging = false;
    this.dragState.imageType = null;
    document.removeEventListener("mousemove", this.handleMouseMove);
    document.removeEventListener("mouseup", this.handleMouseUp);
  }

  async loadImagesFromAttachments() {
    const loadImage = async (attachmentId) => {
      if (!attachmentId) return null;
      try {
        let id = attachmentId;
        if (Array.isArray(attachmentId)) {
          id = attachmentId[0]; 
        }
        id = Number.parseInt(id, 10);
        if (isNaN(id)) {
          console.error("Invalid attachment ID:", attachmentId);
          return null;
        }
        console.log("Loading attachment ID:", id);
        const [attachment] = await this.orm.read(
          "ir.attachment",
          [id],
          ["datas"]
        );
        if (attachment?.datas) {
          return `data:image/png;base64,${attachment.datas}`;
        }
      } catch (error) {
        console.error("Error loading attachment:", error);
      }
      return null;
    };

    if (this.state.widthImageAttachmentId) {
      this.state.widthImage = await loadImage(
        this.state.widthImageAttachmentId
      );
    }
    if (this.state.heightImageAttachmentId) {
      this.state.heightImage = await loadImage(
        this.state.heightImageAttachmentId
      );
    }
    if (this.state.widthImage2AttachmentId) {
      this.state.widthImage2 = await loadImage(
        this.state.widthImage2AttachmentId
      );
    }
    if (this.state.heightImage2AttachmentId) {
      this.state.heightImage2 = await loadImage(
        this.state.heightImage2AttachmentId
      );
    }
  }
}

registry.category("fields").add("calibration_widget", {
  component: CalibrationWidget,
  supportedTypes: ["json", "text", "char"],
});

export default CalibrationWidget;
