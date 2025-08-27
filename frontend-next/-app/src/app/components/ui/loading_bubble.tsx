export default function LoadingBubble() {
  return (
    <div
      role="status"
      aria-label="Assistant is typing"
      className="flex items-center gap-1"
    >
      <span className="block w-2 h-2 rounded-full bg-current opacity-70 animate-[bounce_0.6s_infinite]"></span>
      <span className="block w-2 h-2 rounded-full bg-current opacity-70 animate-[bounce_0.6s_infinite_0.2s]"></span>
      <span className="block w-2 h-2 rounded-full bg-current opacity-70 animate-[bounce_0.6s_infinite_0.4s]"></span>
    </div>
  )
}