/** @odoo-module **/

export function safeErrorString(error) {
    if (error instanceof Error) {
      return error.message || error.stack || error.toString()
    }
    if (typeof error === "object" && error !== null) {
      try {
        const seen = new WeakSet()
        return JSON.stringify(
          error,
          (key, value) => {
            if (typeof value === "object" && value !== null) {
              if (seen.has(value)) {
                return
              }
              seen.add(value)
            }
            return value
          },
        )
      } catch (e) {
        return `[Unstringifiable Object Error: ${e.message || String(e)}]`
      }
    }
    return String(error)
  }
  
  export function formatCurrency(amount) {
    if (amount === undefined || amount === null) return "$0"

    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(amount)
    } catch (error) {
      console.error("Error formatting currency:", safeErrorString(error))
      return "$" + (Number.parseFloat(amount) || 0)
    }
  }
  
  export function getServiceClass(serviceName) {
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
  
  export function isServiceSelected(serviceName, state) {
    if (!state.formData.tag_ids || !Array.isArray(state.formData.tag_ids)) {
      return false
    }
    const selectedServiceNames = state.formData.tag_ids.map((tag) => tag[1])
    return selectedServiceNames.includes(serviceName)
  }
  
  export function isServiceTypeSelected(serviceType, state) {
    const serviceNames = state.formData.tag_ids.map((tag) => tag[1])
  
    if (serviceType === "development") {
      return serviceNames.some((name) => name.toLowerCase().includes("development"))
    } else if (serviceType === "production") {
      return serviceNames.some((name) => name.toLowerCase().includes("production"))
    } else if (serviceType === "swatch") {
      return serviceNames.some(
        (name) => name.toLowerCase().includes("swatch") || name.toLowerCase().includes("swatch packages"),
      )
    } else if (serviceType === "grading") {
      return serviceNames.some((name) => name.toLowerCase().includes("grading"))
    } else if (serviceType === "reverse") {
      return serviceNames.some((name) => name.toLowerCase().includes("reverse"))
    }
    return false
  }

export function sanitizeDecimalInput(value, maxDecimals = 2) {
  if (value === undefined || value === null) {
    return ""
  }
  const stringValue = value.toString()
  const cleaned = stringValue.replace(/[^\d.]/g, "")
  if (cleaned === "") {
    return ""
  }
  const parts = cleaned.split(".")
  const integerPart = parts[0] || ""
  if (parts.length === 1) {
    return integerPart
  }
  const decimalPart = parts.slice(1).join("")
  const limitedDecimal = decimalPart.slice(0, maxDecimals)
  if (limitedDecimal.length > 0) {
    return `${integerPart}.${limitedDecimal}`
  }
  return `${integerPart}.`
}

export function formatDecimalDisplay(value, maxDecimals = 2) {
  if (value === undefined || value === null || value === "") {
    return ""
  }
  if (typeof value === "number") {
    return value.toFixed(maxDecimals)
  }
  return value
}

export function parseDecimalValue(value, defaultValue = 0) {
  if (value === undefined || value === null || value === "") {
    return defaultValue
  }
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? parsed : defaultValue
}
