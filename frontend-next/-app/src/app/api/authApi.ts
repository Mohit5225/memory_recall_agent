import axios from "axios"

// Axios instance for consistent config (expandable for interceptors, baseURL, etc.)
const api = axios.create({
  baseURL: "http://localhost:8000", // Adjust if you use a proxy
  withCredentials: true, // Always send cookies (for JWT httpOnly)
})

// Fetch current user info from /auth/me
export const getCurrentUser = async () => {
  const response = await api.get("/auth/me")
  return response.data
}

// Logout user via /auth/logout
export const logoutUser = async () => {
  const response = await api.post("/auth/logout")
  return response.data
}