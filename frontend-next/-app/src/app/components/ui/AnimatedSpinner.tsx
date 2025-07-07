import React from "react"
import "./Spinner.css"

/**
 * AnimatedSpinner: A visually engaging loading spinner using CSS keyframes.
 * - Uses 3 bouncing colored dots for a lively effect (not just a boring circle).
 * - Accessible: includes aria-label for screen readers.
 * - No external dependencies, pure CSS.
 */
const AnimatedSpinner: React.FC<{ label?: string }> = ({ label = "Loading..." }) => (
  <div className="spinner-container" role="status" aria-label={label}>
    <div className="spinner-dot spinner-dot1" />
    <div className="spinner-dot spinner-dot2" />
    <div className="spinner-dot spinner-dot3" />
    <span className="sr-only">{label}</span>
  </div>
)

export default AnimatedSpinner
