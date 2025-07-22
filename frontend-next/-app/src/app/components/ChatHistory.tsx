import { useEffect, useRef } from 'react'
import ChatBubble from './ChatBubble'
import LoadingBubble from './ui/loading_bubble'
import { cn } from '@/lib/utils'

export interface ChatHistoryProps {
  messages: { sender: 'user' | 'bot'; text: string }[]
  isLoading: boolean
  className?: string
}

export default function ChatHistory({ messages, isLoading, className }: ChatHistoryProps) {
  const scrollAreaRef = useRef<HTMLDivElement>(null)

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
      {messages.map((message, index) => (
        <ChatBubble
          key={index}
          role={message.sender}
          content={message.text}
        />
      ))}
      {isLoading && <LoadingBubble />}
    </div>
  )
}
