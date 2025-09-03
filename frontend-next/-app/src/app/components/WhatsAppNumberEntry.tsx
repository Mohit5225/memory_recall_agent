"use client"
import React, { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useDispatch } from "react-redux"
import dynamic from "next/dynamic"
import axios from "axios"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import AnimatedSpinner from "@/components/ui/AnimatedSpinner"
import { fetchCurrentUser } from "@/app/store/authSlice"
import { Icons } from "./ui/icons"

// Dynamically import PhoneInput to avoid SSR issues
const PhoneInput = dynamic(() => import("react-phone-input-2"), { ssr: false })
import "react-phone-input-2/lib/style.css"

const WhatsAppNumberEntry: React.FC = () => {
  const router = useRouter()
  const dispatch = useDispatch()
  const [phone, setPhone] = useState("")
  const [isValid, setIsValid] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [otpSent, setOtpSent] = useState(false)
  const [resendCooldown, setResendCooldown] = useState(0)
  const [otp, setOtp] = useState("")
  const [otpLoading, setOtpLoading] = useState(false)
  const [otpSuccess, setOtpSuccess] = useState(false)
  const [countryData, setCountryData] = useState({ dialCode: "91" }) // Default to India's code

  // Fixed validation: Properly separate country code from the phone number
  const validatePhone = (value: string, country: any) => {
    // Extract just the number without country code
    const countryCode = country?.dialCode || countryData.dialCode;
    const numberWithoutCode = value.replace(/[^0-9]/g, "").substring(countryCode.length);
    
    // For most countries, mobile numbers should be at least 10 digits
    return numberWithoutCode.length >= 10;
  }

  // Handle phone number change with improved validation
  const handleChange = (value: string, country: any) => {
    setPhone(value)
    setCountryData({ dialCode: country.dialCode })
    setIsValid(validatePhone(value, country))
    setError("")
  }

  // Handle form submission
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

  // Handle OTP input change
  const handleOtpChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.replace(/[^0-9]/g, "")
    setOtp(value)
  }

  // Cooldown timer effect
  useEffect(() => {
    if (resendCooldown > 0) {
      const timer = setTimeout(() => setResendCooldown((s) => s - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [resendCooldown])

  // Redirect after successful OTP verification
  useEffect(() => {
    if (otpSuccess) {
      dispatch(fetchCurrentUser() as any)
      const timer = setTimeout(() => router.push("/dashboard"), 1500)
      return () => clearTimeout(timer)
    }
  }, [otpSuccess, router, dispatch])

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[#0f1724] via-[#121212] to-[#1a1033]">
      {/* Custom scrollbar styles - Add to root element */}
      <style jsx global>{`
        .react-tel-input .country-list::-webkit-scrollbar {
          width: 6px;
        }
        .react-tel-input .country-list::-webkit-scrollbar-track {
          background: #2A2139;
        }
        .react-tel-input .country-list::-webkit-scrollbar-thumb {
          background: #7C3AED;
          border-radius: 3px;
        }
        .react-tel-input .country-list .country.highlight,
        .react-tel-input .country-list .country:hover {
          background-color: #3A2D5D !important;
        }
        .react-tel-input .selected-flag:hover,
        .react-tel-input .selected-flag:focus {
          background-color: rgba(124, 58, 237, 0.1) !important;
        }
      `}</style>

      <Card className="w-full max-w-md bg-[#1f1b2b]/70 backdrop-blur-md shadow-2xl rounded-2xl ring-1 ring-white/5 border-none">
        <CardHeader className="relative pb-3">
          {/* soft top accent that blends with background */}
          <div className="absolute -top-4 left-1/2 transform -translate-x-1/2 w-36 h-24 rounded-full opacity-20 blur-3xl bg-gradient-to-r from-[#7C3AED] to-[#9575CD]"></div>

          <div className="flex items-center justify-center mb-2 mt-3">
            <div className="w-12 h-12 rounded-full bg-gradient-to-r from-[#7C3AED]/80 to-[#9575CD]/80 flex items-center justify-center shadow-md">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 text-white">
                <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
              </svg>
            </div>
          </div>

          <CardTitle className="text-center text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-[#E0C3FC] to-[#8EC5FC] font-jura">WhatsApp Verification</CardTitle>
          <p className="text-center text-[#D1C7F6] text-sm font-jura">
            {!otpSent ? "Link your WhatsApp for memory reinforcement" : !otpSuccess ? "Enter the verification code" : "Verification successful!"}
          </p>
        </CardHeader>

        <CardContent className="pt-6">
          {!otpSent ? (
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="space-y-2">
                <label className="text-[#E5E7EB] font-jura text-sm font-medium">Enter your WhatsApp number</label>
                <div className="phone-input-wrapper">
                  <PhoneInput
                    country={'in'}
                    value={phone}
                    onChange={handleChange}
                    enableSearch
                    inputProps={{
                      name: 'whatsapp',
                      required: true,
                      autoFocus: true,
                    }}
                  containerClass="!w-full !mb-4"
  inputClass="!w-full !bg-transparent !text-gray-200 !text-base !py-3 !px-12 !rounded-lg !border !border-gray-600/35"
  buttonClass="!absolute !left-0 !h-full !bg-transparent !border-r-0 !border-gray-600/35 !rounded-l-lg !z-10"
  dropdownClass="!bg-[#1d1b23] !text-gray-200 !border-gray-700"
  searchClass="!bg-[#2A2139] !text-gray-200 !border-gray-700 !my-2 !mx-auto"
  searchPlaceholder="Search country..."
  countryCodeEditable={false}
                  />
                  <div className="text-xs text-[#A8A4C4] mt-1 px-2">
                    Please enter at least 10 digits after country code
                  </div>
                </div>
              </div>

              <Button
                type="submit"
                disabled={!isValid || loading}
                className="w-full py-5 bg-gradient-to-r from-[#7C3AED]/90 to-[#9575CD]/85 hover:from-[#6D28D9]/90 hover:to-[#8B5CF6]/90 text-white font-jura shadow-lg ring-1 ring-purple-900/10"
              >
                {loading ? (
                  <AnimatedSpinner label="Sending..." />
                ) : (
                  <>
                    <Icons.Send className="mr-2 h-4 w-4" />
                    Send OTP
                  </>
                )}
              </Button>

              {error && (
                <Alert variant="destructive" className="mt-2 bg-[#350c0c] border-[#B71C1C]">
                  <AlertDescription className="text-[#F1F5F9]">{error}</AlertDescription>
                </Alert>
              )}
            </form>
          ) : !otpSuccess ? (
            <form onSubmit={handleVerifyOtp} className="space-y-6">
              <div className="space-y-4">
                <label className="text-[#E5E7EB] text-sm font-medium font-jura block text-center">
                  Enter the 6-digit verification code sent to your WhatsApp
                </label>

                <div className="relative">
                  <div className="absolute -inset-0.5 bg-gradient-to-r from-[#7C3AED]/40 to-[#9575CD]/40 rounded-lg blur opacity-30"></div>
                  <input
                    type="text"
                    value={otp}
                    onChange={handleOtpChange}
                    maxLength={6}
                    pattern="\\d{6}"
                    className="relative bg-transparent border border-[#4B5563] rounded-lg px-4 py-3 text-center text-xl tracking-widest w-full text-[#E5E7EB] font-mono"
                    placeholder="••••••"
                    autoFocus
                    required
                  />
                </div>

                <div className="text-center text-sm text-[#C9BFF6] font-jura">
                  Didn't receive the code?{' '}
                  <button
                    type="button"
                    onClick={handleResend}
                    disabled={resendCooldown > 0 || loading}
                    className="text-[#D8CCFF] hover:text-[#F1F5F9] transition-colors disabled:opacity-50"
                  >
                    {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend"}
                  </button>
                </div>
              </div>

              <Button
                type="submit"
                disabled={otp.length !== 6 || otpLoading}
                className="w-full py-5 bg-gradient-to-r from-[#7C3AED]/90 to-[#9575CD]/85 hover:from-[#6D28D9]/90 hover:to-[#8B5CF6]/90 text-white font-jura shadow-lg ring-1 ring-purple-900/10"
              >
                {otpLoading ? (
                  <AnimatedSpinner label="Verifying..." />
                ) : (
                  "Verify OTP"
                )}
              </Button>

              {error && (
                <Alert variant="destructive" className="mt-2 bg-[#350c0c] border-[#B71C1C]">
                  <AlertDescription className="text-[#F1F5F9]">{error}</AlertDescription>
                </Alert>
              )}
            </form>
          ) : (
            <div className="py-8 text-center space-y-4">
              <div className="w-16 h-16 mx-auto rounded-full bg-[#2E7D32] flex items-center justify-center shadow-inner">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-[#F1F5F9]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-[#E5E7EB] text-xl font-jura">WhatsApp Verified!</p>
              <p className="text-[#C9BFF6] text-sm font-jura">Redirecting to dashboard...</p>
              <AnimatedSpinner label="Redirecting..." />
            </div>
          )}

          {/* Information section */}
          {!otpSuccess && (
            <div className="mt-6 pt-6 border-t border-[#2b2b3a] text-sm text-[#C9BFF6] font-jura">
              <h4 className="font-medium text-[#E5E7EB] mb-2">Why we need your WhatsApp</h4>
              <p className="text-[#D6D3FF]/90">We'll send you personalized memory reinforcement nuggets through WhatsApp to help you retain knowledge better.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default WhatsAppNumberEntry