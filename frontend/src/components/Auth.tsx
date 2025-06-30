import { Button } from "@/components/ui/button" // Imports the shadcn/ui Button component for consistent UI

// Auth component: renders a login screen with a "Login with Google" button
export default function Auth() {
  // Handler for button click: redirects to backend OAuth endpoint
  const handleGoogleLogin = () => {
    // Full-page redirect to backend /auth/google (initiates OAuth handshake)
    window.location.href = "http://localhost:8000/auth/google"
    // Why not fetch()? Because OAuth must be a browser redirect for security (cookies, CSRF, etc.)
  }

  // Render a centered card with the login button
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="rounded-lg shadow-lg p-8 bg-card flex flex-col items-center">
        <h2 className="text-2xl font-bold mb-6">Sign in to continue</h2>
        <Button
          variant="default"
          size="lg"
          className="w-full"
          onClick={handleGoogleLogin}
        >
          Continue with Google
        </Button>
      </div>
    </div>
  )
}