import React, { useEffect } from "react"
import { useSelector, useDispatch } from "react-redux"
import type { RootState } from "@/store"
import { fetchCurrentUser, logout } from "@/store/authSlice"
import { Button } from "@/components/ui/button"
import AnimatedSpinner from "@/components/ui/AnimatedSpinner"
import { useNavigate } from "react-router-dom"

const Dashboard: React.FC = () => {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { user, isAuthenticated, authStatus } = useSelector((state: RootState) => state.auth)

  // On mount, fetch user if not loaded
  useEffect(() => {
    if (!user && authStatus !== "loading") {
      dispatch(fetchCurrentUser() as any)
    }
  }, [user, authStatus, dispatch])

  // If not authenticated, redirect to /auth
  useEffect(() => {
    if (authStatus === "error" || (!user && authStatus !== "loading")) {
      navigate("/auth")
    }
  }, [authStatus, user, navigate])

  if (authStatus === "loading" || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <AnimatedSpinner label="Loading dashboard..." />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-100 to-zinc-300 dark:from-zinc-900 dark:to-zinc-800 flex flex-col items-center py-12">
      <div className="bg-card rounded-xl shadow-xl p-8 w-full max-w-lg flex flex-col items-center">
        <h1 className="text-3xl font-bold mb-2">Dashboard</h1>
        <p className="text-muted-foreground mb-6">Welcome, <span className="font-semibold">{user.display_name}</span>!</p>
        <div className="w-full mb-6">
          <div className="flex flex-col gap-2">
            <div>
              <span className="font-medium">Email:</span> {user.email}
            </div>
            <div>
              <span className="font-medium">WhatsApp:</span>{" "}
              {user.whatsapp_number ? (
                <span>
                  {user.whatsapp_number}{" "}
                  {user.whatsapp_verified ? (
                    <span className="text-green-600 ml-2">✔️ Verified</span>
                  ) : (
                    <span className="text-yellow-600 ml-2">⏳ Not Verified</span>
                  )}
                </span>
              ) : (
                <span className="text-muted-foreground">Not set</span>
              )}
            </div>
            <div>
              <span className="font-medium">Roles:</span> {user.roles.join(", ")}
            </div>
          </div>
        </div>
        <Button
          variant="destructive"
          className="w-full"
          onClick={() => dispatch(logout() as any)}
        >
          Logout
        </Button>
      </div>
      <div className="mt-10 w-full max-w-lg">
        <div className="bg-card rounded-lg shadow p-6 flex flex-col items-center">
          <h2 className="text-xl font-semibold mb-2">🚧 Widgets Coming Soon</h2>
          <p className="text-muted-foreground text-center">
            This is your dashboard. Future widgets (reminders, stats, etc.) will appear here.
          </p>
        </div>
      </div>
    </div>
  )
}

export default Dashboard