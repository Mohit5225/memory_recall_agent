import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'

export interface ChatBubbleProps {
  sender: 'user' | 'assistant'
  text: string
}

export default function ChatBubble({ sender, text }: ChatBubbleProps) {
  const isUser = sender === 'user'

  return (
    <div className={cn('py-2', isUser ? 'flex justify-end' : 'flex justify-start font-jura')}>
      <div
        className={cn(
          'max-w-[43.5rem]', // Retain fixed max-width for readability
          isUser ? 'ml-auto pl-10' : 'mr-auto' // Alignment without avatar
        )}
      >
        {/* Message content (now the only element) */}
        <div className="min-w-0"> {/* Simplified; no flex-1 needed without avatar */}
          <div className={cn(
            'prose prose-sm break-words text-[#F1F5F9] font-jura',
            'font-semibold',
            isUser && 'text-right'
          )}>
            <ReactMarkdown>{text}</ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  )
}