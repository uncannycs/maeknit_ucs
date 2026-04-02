/** @odoo-module **/

export class ServiceManager {
  static getServiceClass(serviceName) {
    const serviceNameLower = serviceName.toLowerCase()

    if (serviceNameLower.includes("development")) {
      return "development"
    } else if (serviceNameLower.includes("production")) {
      return "production"
    } else if (serviceNameLower.includes("reverse") || serviceNameLower.includes("reverse engineering")) {
      return "reverse"
    } else if (serviceNameLower.includes("programming")) {
      return "programming"
    } else if (serviceNameLower.includes("swatch") || serviceNameLower.includes("swatch packages")) {
      return "swatching"
    } else if (serviceNameLower.includes("grading")) {
      return "grading"
    }

    return ""
  }

  static isServiceType(serviceName, serviceType) {
    const serviceNameLower = serviceName.toLowerCase()

    if (serviceType === "development") {
      return serviceNameLower.includes("development")
    } else if (serviceType === "production") {
      return serviceNameLower.includes("production")
    } else if (serviceType === "swatch") {
      return serviceNameLower.includes("swatch") || serviceNameLower.includes("swatch packages")
    } else if (serviceType === "programming") {
      return serviceNameLower.includes("programming")
    } else if (serviceType === "reverse") {
      return serviceNameLower.includes("reverse") || serviceNameLower.includes("reverse engineering")
    } else if (serviceType === "grading") {
      return serviceNameLower.includes("grading")
    }

    return false
  }
}
