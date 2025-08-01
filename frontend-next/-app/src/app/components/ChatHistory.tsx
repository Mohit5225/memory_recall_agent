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
        'flex flex-col space-y-4 overflow-y-auto p-4',
        className
      )}
    >
      {messages.length === 0 && !isLoading && (
        <div className="text-center text-gray-500 py-8">
          No messages yet. Start a conversation!
        </div>
      )}
      {messages.map((message, index) => {
        console.log(`Rendering message ${index}:`, message);
        return (
          <ChatBubble
            key={index}
            sender={message.sender}
            text={message.text}
          />
        );
      })}
      {isLoading && <LoadingBubble />}
    </div>
  )
}