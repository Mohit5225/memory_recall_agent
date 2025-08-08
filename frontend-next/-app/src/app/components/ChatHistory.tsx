import { useEffect, useRef } from 'react'
import ChatBubble from './ChatBubble'
import LoadingBubble from './ui/loading_bubble'
import { cn } from '@/lib/utils'

export interface ChatHistoryProps {
  messages: { sender: 'user' | 'assistant'; text: string }[]
  isLoading: boolean
  className?: string
}

export default function ChatHistory({ messages, isLoading, className }: ChatHistoryProps) {
  const scrollAreaRef = useRef<HTMLDivElement>(null)

  // Debug logging
  console.log("ChatHistory render - messages:", messages);
  console.log("ChatHistory render - messages length:", messages.length);
  console.log("ChatHistory render - isLoading:", isLoading);

  useEffect(() => {
    if (scrollAreaRef.current) {
      scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight
    }
  }, [messages, isLoading])

  return (
    <div
      ref={scrollAreaRef}
      className={cn(
        'relative flex flex-col space-y-6.5 overflow-y-auto p-4 pb-32', // Added 'relative'
        className
      )}
    >
      {/* Radial Glow Background */}
      <div
        className="absolute inset-0 z-0 pointer-events-none"
        style={{
          backgroundImage: "radial-gradient(circle 500px at 50% 200px, #3e3e3e, transparent)",
        }}
      />
      
      {/* Message Content */}
      <div className="relative z-10 flex flex-col space-y-6.5">
        {messages.length === 0 && !isLoading && (
          <div className="text-center text-gray-500 py-8">
            No messages yet. Start a conversation!
          </div>
        )}
        
        {messages.map((message, index) => (
          <ChatBubble 
            key={index}
            sender={message.sender}
            text={message.text}
          />
        ))}
        
        {isLoading && <LoadingBubble />}
      </div> {/* This closing tag was misplaced */}
    </div>
  )
}
