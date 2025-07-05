import { Button } from "@/components/ui/button"
import { useNavigate } from "react-router-dom"

const Landing = () => {
  const navigate = useNavigate()
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="rounded-lg shadow-lg p-8 bg-card flex flex-col items-center min-w-[320px]">
        <h1 className="text-3xl font-bold mb-4">Welcome to Memory Recall Agent</h1>
        <p className="mb-6 text-muted-foreground text-center">
          Your AI-powered reminder and scheduling assistant.
        </p>
        <Button
          variant="default"
          size="lg"
          className="w-full"
          onClick={() => navigate("/auth")}
        >
          Get Started
        </Button>
      </div>
    </div>
  )
}

export default Landing