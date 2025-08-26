import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'

export interface ChatBubbleProps {
  sender: 'user' | 'assistant'
  text: string
}

export default function ChatBubble({ sender, text }: ChatBubbleProps) {
  const isUser = sender === 'user'

  return (
    <div className={cn('py-2', isUser ? 'flex justify-end' : 'flex justify-start')}>
      <div
        className={cn(
          'max-w-2xl', // Retain fixed max-width for readability
          isUser ? 'ml-auto' : 'mr-auto' // Alignment without avatar
        )}
      >
        {/* Message content (now the only element) */}
        <div className="min-w-0"> {/* Simplified; no flex-1 needed without avatar */}
          <div className={cn(
            'prose prose-sm break-words text-[#F1F5F9]',
            isUser && 'text-right'
          )}>
            <ReactMarkdown>{text}</ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  )
}
