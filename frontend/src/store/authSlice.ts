import { createSlice, createAsyncThunk } from "@reduxjs/toolkit"
import type { PayloadAction } from "@reduxjs/toolkit"
import { getCurrentUser, logoutUser } from "../api/authApi"

// --- Interfaces ---
interface User {
  user_id: string
  display_name: string
  email: string
  roles: string[]
  whatsapp_number: string | null
  whatsapp_verified: boolean
  // Add more fields if /auth/me returns them (e.g., last_login)
}

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  authStatus: "idle" | "loading" | "authenticated" | "error"
  error: string | null
}

// --- Initial State ---
const initialState: AuthState = {
  user: null,
  isAuthenticated: false,
  authStatus: "idle",
  error: null,
}

// --- Thunks ---
// Fetch current user info from backend
export const fetchCurrentUser = createAsyncThunk(
  "auth/fetchCurrentUser",
  async (_, { rejectWithValue }) => {
    try {
      const data = await getCurrentUser()
      return data
    } catch (error: any) {
      // Axios error handling: error.response?.status === 401 means not authenticated
      if (error.response && error.response.status === 401) {
        return rejectWithValue("Not authenticated")
      }
      return rejectWithValue(error.message || "Network error")
    }
  }
)

// Logout thunk: calls backend and clears state
export const logout = createAsyncThunk(
  "auth/logout",
  async (_, { rejectWithValue }) => {
    try {
      await logoutUser()
      return true
    } catch (error: any) {
      return rejectWithValue(error.message || "Logout failed")
    }
  }
)

// --- Slice ---
const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    // Manual logout reducer (can be used for instant UI logout)
    logout(state) {
      state.user = null
      state.isAuthenticated = false
      state.authStatus = "idle"
      state.error = null
    },
  },
  extraReducers: (builder) => {
    builder
      // fetchCurrentUser
      .addCase(fetchCurrentUser.pending, (state) => {
        state.authStatus = "loading"
        state.error = null
      })
      .addCase(fetchCurrentUser.fulfilled, (state, action: PayloadAction<User>) => {
        state.user = action.payload
        state.isAuthenticated = true
        state.authStatus = "authenticated"
        state.error = null
      })
      .addCase(fetchCurrentUser.rejected, (state, action) => {
        state.user = null
        state.isAuthenticated = false
        state.authStatus = "error"
        state.error = action.payload as string
      })
      // logout thunk
      .addCase(logout.fulfilled, (state) => {
        state.user = null
        state.isAuthenticated = false
        state.authStatus = "idle"
        state.error = null
      })
      .addCase(logout.rejected, (state, action) => {
        state.error = action.payload as string
      })
  },
})

export const { logout: logoutReducer } = authSlice.actions
export default authSlice.reducer