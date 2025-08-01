'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useSelector, useDispatch } from 'react-redux'
 
import Dashboard from "../components/Dashboard"
import { fetchCurrentUser } from '@/app/store/authSlice'
import type { RootState } from "@/app/store"
import AnimatedSpinner from '@/components/ui/AnimatedSpinner'

export default function DashboardPage() {
  const router = useRouter()
  const dispatch = useDispatch()
  const { user, authStatus } = useSelector((state: RootState) => state.auth)

  useEffect(() => {
    // If no user data and not already loading, fetch it
    if (!user && authStatus === 'idle') {
      dispatch(fetchCurrentUser() as any)
    }
  }, [user, authStatus, dispatch])

 
 // Show loading while checking auth or in the initial idle state before the first fetch
  if (authStatus === 'loading' || authStatus === 'idle') {
    return <AnimatedSpinner label="Verifying session..." />
  }

  // Redirect to auth ONLY if authentication has failed.
  if (authStatus === 'error' || !user) {
    router.push('/auth')
    return null
  }

  return <Dashboard />
}