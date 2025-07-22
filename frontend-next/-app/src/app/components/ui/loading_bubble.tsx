import { Icons } from '@/components//ui/icons'
export default function LoadingBubble() {
  return (
    <div className="flex items-start gap-4 rounded-lg bg-[#4B5563]/50 p-4 mr-auto max-w-[70%]">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#5F6483] text-[#F1F5F9]">
        <Icons.Bot className="h-5 w-5" />
      </div>
      <div className="flex items-center gap-1 pt-2">
        <span className="h-2 w-2 animate-[bounce_1s_infinite] rounded-full bg-[#F1F5F9]/70"></span>
        <span className="h-2 w-2 animate-[bounce_1s_infinite_200ms] rounded-full bg-[#F1F5F9]/70"></span>
        <span className="h-2 w-2 animate-[bounce_1s_infinite_400ms] rounded-full bg-[#F1F5F9]/70"></span>
      </div>
    </div>
  )
}