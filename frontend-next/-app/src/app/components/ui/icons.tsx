import { Bot, User, Send, RefreshCw, Download, Sun, Moon, LucideProps } from 'lucide-react'

export const Icons = {
  Bot: (props: LucideProps) => <Bot {...props} />,
  User: (props: LucideProps) => <User {...props} />,
  Send: (props: LucideProps) => <Send {...props} />,
  Reset: (props: LucideProps) => <RefreshCw {...props} />,
  Export: (props: LucideProps) => <Download {...props} />,
  Sun: (props: LucideProps) => <Sun {...props} />,
  Moon: (props: LucideProps) => <Moon {...props} />,
}