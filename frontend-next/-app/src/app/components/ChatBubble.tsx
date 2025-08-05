import { User, Bot } from 'lucide-react'
import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'

export interface ChatBubbleProps {
  sender: 'user' | 'assistant'
  text: string
}

export default function ChatBubble({ sender, text }: ChatBubbleProps) {
  const isUser = sender === 'user'
  const Icon = isUser ? User : Bot

  return (
    <div className="w-full px-[12.5%] py-2"> {/* 25% total margin (12.5% each side) */}
      <div
        className={cn(
          'flex items-start gap-3 max-w-[80%]', // Limit message width
          isUser 
            ? 'ml-auto flex-row-reverse' // Push to right, avatar on right
            : 'mr-auto' // Push to left, avatar on left
        )}
      >
        {/* Avatar */}
        <div
          className={cn(
            'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
            isUser ? 'bg-[#7C3AED]' : 'bg-[#5F6483]'
          )}
        >
          <Icon className="h-5 w-5 text-[#F1F5F9]" />
        </div>
        
        {/* Message content */}
        <div className="flex-1 min-w-0">
          <div className={cn(
            'prose prose-sm max-w-none break-words text-[#F1F5F9]',
            isUser && 'text-right'
          )}>
            <p>{text}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
