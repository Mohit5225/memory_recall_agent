'use client'
import React, { useEffect, forwardRef, useRef, useLayoutEffect } from 'react'
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
    const combinedRef = (ref as React.MutableRefObject<HTMLDivElement | null>) || localRef

    useEffect(() => {
      // Use the combined ref (external if provided, else local)
      const scrollArea = (ref as React.RefObject<HTMLDivElement>)?.current || localRef.current
      if (scrollArea) {
        scrollArea.scrollTop = scrollArea.scrollHeight
      }
    }, [messages, isLoading, ref])

    return (
      <div
        ref={ref || localRef}
        className={cn(
          'relative flex flex-col space-y-6.5 overflow-y-auto p-4',
          className
        )}
      >
        {/* Radial Glow Background */}
        <div
          className="absolute inset-0 z-0 pointer-events-none"
          style={{
            backgroundImage:
              'radial-gradient(circle 500px at 50% 200px, #3e3e3e, transparent)',
          }}
        />
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
          
          {/* Render the children (which will include ChatFooter) */}
          {children}
        </div>
      </div>
    )
  }
)

ChatHistory.displayName = 'ChatHistory'

export default ChatHistory