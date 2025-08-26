// ...existing code...
'use client'
import React, { useEffect, useState } from 'react'

type ChatFooterProps = {
  // optional explicit height in px; when provided it is used as a baseline/fallback
  height?: number
}

/**
 * Responsive ChatFooter spacer:
 * - If `height` prop given => used as baseline but still respects responsive breakpoints.
 * - Otherwise uses sensible defaults: small screens -> 160px, medium -> 120px, large -> 88px.
 * - Recomputes on window resize.
 */
export default function ChatFooter({ height }: ChatFooterProps) {
  const computeHeight = (w: number, explicit?: number) => {
    if (typeof explicit === 'number' && explicit > 0) {
      // allow explicit value but clamp to a sensible min/max for safety
      return Math.max(56, Math.min(explicit, 300))
    }
    if (w < 640) return 160 // sm screens
    if (w < 1024) return 120 // md screens
    return 88 // lg and up
  }

  const [resolved, setResolved] = useState<number>(() =>
    typeof window !== 'undefined' ? computeHeight(window.innerWidth, height) : computeHeight(1024, height)
  )

  useEffect(() => {
    const onResize = () => setResolved(computeHeight(window.innerWidth, height))
    window.addEventListener('resize', onResize)
    // in case parent passed a new height prop, update as well
    return () => window.removeEventListener('resize', onResize)
  }, [height])

  return (
    <div
      // explicit px height so ChatHistory.scrollHeight includes it
      style={{ height: `${resolved}px`, minHeight: `${resolved}px`, width: '100%' }}
      aria-hidden="true"
      data-testid="chat-footer-spacer"
    />
  )
}
// ...existing code...