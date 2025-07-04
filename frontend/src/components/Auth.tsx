import { Button } from "@/components/ui/button" // Imports the shadcn/ui Button component for consistent UI
import React from "react"
import AnimatedSpinner from "@/components/ui/AnimatedSpinner"

// Auth component: renders a login screen with a "Login with Google" button
export default function Auth() {
  // Local state to show spinner while redirecting
  const [loading, setLoading] = React.useState(false)

  // Handler for button click: redirects to backend OAuth endpoint
  const handleGoogleLogin = () => {
    setLoading(true)
    // Give spinner a moment to show before redirect (UX polish)
    setTimeout(() => {
      window.location.href = "http://localhost:8000/auth/google"
    }, 400)
  }

  // Render a centered card with the login button or spinner
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="rounded-lg shadow-lg p-8 bg-card flex flex-col items-center min-w-[320px]">
        <h2 className="text-2xl font-bold mb-6">Sign in to continue</h2>
        {loading ? (
          <>
            <AnimatedSpinner label="Redirecting to Google..." />
            <div className="mt-4 text-muted-foreground text-sm">Redirecting to Google...</div>
          </>
        ) : (
          <Button
            variant="default"
            size="lg"
            className="w-full"
            onClick={handleGoogleLogin}
          >
            Continue with Google
          </Button>
        )}
      </div>
    </div>
  )
}