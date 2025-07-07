import { configureStore } from "@reduxjs/toolkit"
import authReducer from "./authSlice"

// 1. Configures the Redux store with your only slice, 'auth'.
//    This is the "control room" for all Redux state in your app.
export const store = configureStore({
  reducer: {
    auth: authReducer, // Mounts your auth slice at state.auth
  },
})

// 2. RootState type: infers the shape of your Redux state tree.
//    Used for type-safe selectors everywhere.
export type RootState = ReturnType<typeof store.getState>

// 3. AppDispatch type: for type-safe dispatching of thunks/actions.
export type AppDispatch = typeof store.dispatch