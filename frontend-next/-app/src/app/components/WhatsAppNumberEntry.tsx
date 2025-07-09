'use client'

import React, { useState } from "react"
import { useRouter } from "next/navigation"
// import PhoneInput from "react-phone-input-2"
import "react-phone-input-2/lib/style.css"
import axios from "axios"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "../components/ui/alert"
import dynamic from "next/dynamic";
import { useDispatch } from "react-redux"
import { fetchCurrentUser } from "@/app/store/authSlice"
const PhoneInput = dynamic(() => import("react-phone-input-2"), { ssr: false });
const WhatsAppNumberEntry: React.FC = () => {
  // Next.js router for navigation
  const router = useRouter()
  const dispatch = useDispatch()
  const [phone, setPhone] = useState("")
  const [isValid, setIsValid] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [otpSent, setOtpSent] = useState(false)
  const [resendCooldown, setResendCooldown] = useState(0)
  // OTP input state
  const [otp, setOtp] = useState("")
  const [otpLoading, setOtpLoading] = useState(false)
  const [otpSuccess, setOtpSuccess] = useState(false)

  // Minimal validation: must start with + and at least 10 digits
  const validatePhone = (num: string) => /^\+\d{10,}$/.test("+" + num.replace(/[^0-9]/g, ""))

  const handleChange = (value: string) => {
    setPhone(value)
    setIsValid(validatePhone(value))
    setError("")
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError("")
    try {
      await axios.post(
        "http://localhost:8000/auth/whatsapp",
        { whatsapp_number: "+" + phone.replace(/[^0-9]/g, "") },
        { withCredentials: true }
      )
      setOtpSent(true)
      setResendCooldown(60)
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to send OTP")
    } finally {
      setLoading(false)
    }
  }

  // OTP verification handler
  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault()
    setOtpLoading(true)
    setError("")
    try {
      await axios.post(
        "http://localhost:8000/auth/verify-phone",
        { otp },
        { withCredentials: true }
      )
      setOtpSuccess(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to verify OTP")
    } finally {
      setOtpLoading(false)
    }
  }

  // Resend OTP handler
  const handleResend = async () => {
    setLoading(true)
    setError("")
    try {
      await axios.post("http://localhost:8000/auth/send-otp", {}, { withCredentials: true })
      setResendCooldown(60)
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to resend OTP.")
    } finally {
      setLoading(false)
    }
  }

  // Cooldown timer effect
  React.useEffect(() => {
    if (resendCooldown > 0) {
      const timer = setTimeout(() => setResendCooldown(resendCooldown - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [resendCooldown])

  // Redirect to dashboard after successful OTP verification
  React.useEffect(() => {
    if (otpSuccess) {
      // Update auth state then show success and redirect
      dispatch(fetchCurrentUser() as any)
      const timer = setTimeout(() => router.push("/dashboard"), 1500)
      return () => clearTimeout(timer)
    }
  }, [otpSuccess, router, dispatch])

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-zinc-100 to-zinc-300 dark:from-zinc-900 dark:to-zinc-800">
      <Card className="w-full max-w-md shadow-2xl border-2 border-zinc-200 dark:border-zinc-700">
        <CardHeader>
          <CardTitle className="text-center text-2xl font-bold text-primary">WhatsApp Verification</CardTitle>
        </CardHeader>
        <CardContent>
          {!otpSent ? (
            <form onSubmit={handleSubmit} className="flex flex-col gap-6">
              <label className="text-lg font-medium text-center">Enter your WhatsApp number to continue</label>
              <PhoneInput
                country={"in"}
                value={phone}
                onChange={handleChange}
                inputProps={{ name: "whatsapp", required: true, autoFocus: true }}
                inputStyle={{ width: "100%", fontSize: "1.1rem", borderRadius: 8, border: "1px solid #e5e7eb", padding: "0.75rem 1rem" }}
                buttonStyle={{ borderRadius: 8, border: "1px solid #e5e7eb" }}
                containerStyle={{ width: "100%" }}
                enableSearch
                disableDropdown={false}
                masks={{ in: ".....-....." }}
              />
              <Button type="submit" disabled={!isValid || loading} className="w-full text-lg py-2">
                {loading ? "Sending..." : "Send OTP"}
              </Button>
              {error && (
                <Alert variant="destructive" className="mt-2">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
            </form>
          ) : !otpSuccess ? (
            <form onSubmit={handleVerifyOtp} className="flex flex-col gap-6">
              <label className="text-lg font-medium text-center">Enter the OTP sent to your WhatsApp</label>
              <input
                type="text"
                value={otp}
                onChange={e => setOtp(e.target.value)}
                maxLength={6}
                pattern="\d{6}"
                className="w-full border rounded px-4 py-2 text-lg"
                placeholder="Enter 6-digit OTP"
                autoFocus
                required
              />
              <Button type="submit" disabled={otp.length !== 6 || otpLoading} className="w-full text-lg py-2">
                {otpLoading ? "Verifying..." : "Verify OTP"}
              </Button>
              <div className="flex flex-col gap-2 items-center">
                <span className="text-muted-foreground text-sm">Didn't get the code?</span>
                <Button
                  type="button"
                  variant="outline"
                  disabled={resendCooldown > 0 || loading}
                  onClick={handleResend}
                  className="w-full"
                >
                  {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend OTP"}
                </Button>
              </div>
              {error && (
                <Alert variant="destructive" className="mt-2">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
            </form>
          ) : (
            <div className="flex flex-col gap-4 items-center justify-center py-8">
              <span className="text-green-600 text-lg font-semibold">Phone number verified successfully! Redirecting...</span>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default WhatsAppNumberEntry
