import { BrowserRouter, Routes, Route } from "react-router-dom"

import Landing from "@/components/Landing"
import Auth from "@/components/Auth"
// import AuthCallback from "@/components/AuthCallback" // (if/when you add it)
import Dashboard from "@/components/Dashboard" // (stub for now)

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/auth" element={<Auth />} />
        <Route path="/dashboard" element={<Dashboard />} />
        {/* <Route path="/auth/callback" element={<AuthCallback />} /> */}
      </Routes>
    </BrowserRouter>
  )
}