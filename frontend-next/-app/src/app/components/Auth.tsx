'use client'
import { Button } from "@/components/ui/button"
import React from "react"
import AnimatedSpinner from "@/components/ui/AnimatedSpinner"
import { Icons } from "./ui/icons"

export default function Auth() {
  const [loading, setLoading] = React.useState(false)

  const handleGoogleLogin = () => {
    setLoading(true)
    setTimeout(() => {
      window.location.href = "http://localhost:8000/auth/google"
    }, 400)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[#1A1A1A] to-[#2D2D2D]">
      <div className="w-full max-w-md p-8 space-y-8">
        {/* Animated logo/brand element */}
        <div className="flex flex-col items-center justify-center space-y-2">
          <div className="relative w-24 h-24 mb-4">
            <div className="absolute inset-0 rounded-full bg-gradient-to-r from-[#7C3AED] to-[#9575CD] opacity-70 blur-lg"></div>
            <div className="absolute inset-0 rounded-full bg-gradient-to-r from-[#7C3AED] to-[#9575CD] flex items-center justify-center">
              <svg viewBox="0 0 24 24" className="w-12 h-12 text-[#F1F5F9]" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 17.75C12.4142 17.75 12.75 17.4142 12.75 17C12.75 16.5858 12.4142 16.25 12 16.25C11.5858 16.25 11.25 16.5858 11.25 17C11.25 17.4142 11.5858 17.75 12 17.75Z" fill="currentColor" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M12 13.75V14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M12 10.75V4.75" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M8.75 7.75H3.75V19.25H20.25V7.75H15.25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
          </div>
          <h1 className="text-3xl font-bold text-[#F1F5F9] font-jura">Memory Recall</h1>
          <p className="text-[#4B5563] text-center max-w-xs font-jura">Your Second Brain for Memory Reinforcement</p>
        </div>

        {/* Auth card */}
        <div className="rounded-lg bg-[#2D2D2D] border border-[#4B5563] shadow-xl p-6 space-y-6">
          <h2 className="text-xl font-semibold text-[#F1F5F9] text-center font-jura">Sign in to continue</h2>
          
          {loading ? (
            <div className="flex flex-col items-center justify-center space-y-3">
              <AnimatedSpinner label="Redirecting to Google..." />
              <p className="text-[#9575CD] text-sm font-jura">Redirecting to Google...</p>
            </div>
          ) : (
            <div className="space-y-4">
              <Button
                variant="default"
                size="lg"
                onClick={handleGoogleLogin}
                className="w-full bg-gradient-to-r from-[#7C3AED] to-[#9575CD] hover:from-[#6D28D9] hover:to-[#8B5CF6] text-[#F1F5F9] py-6 font-jura"
              >
                <Icons.Bot className="mr-2 h-5 w-5" />
                Continue with Google
              </Button>
            </div>
          )}
        </div>

        {/* Info cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-8">
          <div className="rounded-lg bg-[#2D2D2D] border border-[#4B5563] p-4">
            <h3 className="text-[#F1F5F9] font-semibold mb-2 font-jura">Reinforced Learning</h3>
            <p className="text-[#4B5563] text-sm font-jura">Get timed reminders on topics you're learning to improve retention</p>
          </div>
          <div className="rounded-lg bg-[#2D2D2D] border border-[#4B5563] p-4">
            <h3 className="text-[#F1F5F9] font-semibold mb-2 font-jura">WhatsApp Integration</h3>
            <p className="text-[#4B5563] text-sm font-jura">Receive knowledge nuggets on your mobile via WhatsApp</p>
          </div>
        </div>
      </div>
    </div>
  )
}