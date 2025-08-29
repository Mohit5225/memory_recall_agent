"use client"
import React, { forwardRef, useRef, useLayoutEffect } from 'react'
import ChatBubble from './ChatBubble'
import LoadingBubble from './ui/loading_bubble'
import { cn } from '@/lib/utils'
 
export interface ChatHistoryProps {
  messages: { sender: 'user' | 'assistant'; text: string }[]
  isLoading: boolean
  className?: string
  children?: React.ReactNode
}

// We wrap the component with React.forwardRef to accept external refs.
const ChatHistory = forwardRef<HTMLDivElement, ChatHistoryProps>(
  ({ messages, isLoading, className, children }, ref) => {
    // Fallback local ref in case no ref is provided
    const localRef = useRef<HTMLDivElement>(null)

    // Combine forwarded ref (function or object) with our localRef
    const setCombinedRef = (node: HTMLDivElement | null) => {
      // Always keep localRef updated so internal logic can rely on it
      localRef.current = node
      if (!ref) return
      if (typeof ref === 'function') {
        ref(node)
      } else {
        ;(ref as React.MutableRefObject<HTMLDivElement | null>).current = node
      }
    }

    // Scroll to bottom after messages/loading state updates, before paint to avoid flicker
    useLayoutEffect(() => {
      const el = localRef.current
      if (el) {
        el.scrollTop = el.scrollHeight
      }
    }, [messages, isLoading])

    return (
      <div
        ref={setCombinedRef}
        className={cn(
          // ...existing code...
          'relative flex flex-col space-y-6.5 overflow-y-auto  scrollbar-thin scrollbar-thumb-[#7C3AED] scrollbar-track-[#2A1A4A]',
          className
        )}
      >
      
        {/* Message Content */}
        <div className="relative z-10 flex flex-col space-y-6.5 max-w-4xl mx-auto">
          {messages.length === 0 && !isLoading && (
            <div className="text-center text-gray-500 py-8">
              No messages yet. Start a conversation!
            </div>
          )}
          {messages.map((message, index) => (
            <ChatBubble key={index} sender={message.sender} text={message.text} />
          ))}
          {isLoading && <LoadingBubble />}
        </div>
      </div>
    )
  }
)

ChatHistory.displayName = 'ChatHistory'

export default ChatHistory