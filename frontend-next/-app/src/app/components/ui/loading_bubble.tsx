import React from 'react';

export default function LoadingBubble() {
  return (
    <div className="flex items-center gap-1">
      <span className="h-1.5 w-1.5 animate-[bounce_0.8s_infinite] rounded-full bg-[#7C3AED]"></span>
      <span className="h-1.5 w-1.5 animate-[bounce_0.8s_infinite_150ms] rounded-full bg-[#7C3AED]"></span>
      <span className="h-1.5 w-1.5 animate-[bounce_0.8s_infinite_300ms] rounded-full bg-[#7C3AED]"></span>
    </div>
  );
}