import { User, Bot } from 'lucide-react'
import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'
import { Assistant } from 'next/font/google'

export interface ChatBubbleProps {
  sender: 'user' | 'assistant'
  text : string
}

export default function ChatBubble({ sender , text }: ChatBubbleProps) {
  const isUser = sender === 'user'
  const Icon = isUser ? User : Bot

  return (
    <div
      className={cn(
        'flex items-start gap-4 rounded-lg p-4',
        isUser
          ? 'flex-row-reverse bg-[#1A1A1A] border border-[#4B5563] ml-auto max-w-[70%] hover:bg-[#7C3AED]/10'
          : 'bg-[#4B5563] border border-[#4B5563] mr-auto max-w-[70%] hover:bg-[#7C3AED]/10'
      )}
    >
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          isUser ? 'bg-[#7C3AED]' : 'bg-[#5F6483]'
        )}
      >
        <Icon className="h-5 w-5 text-[#F1F5F9]" />
      </div>
      <div
        className={cn(
          'prose prose-sm max-w-full break-words text-[#F1F5F9]',
          isUser && 'text-right'
        )}
      >
        {/* Use simple <p> instead of ReactMarkdown if you don't have the dependency */}
        <p>{text}</p>
      </div>
    </div>
  )
}
