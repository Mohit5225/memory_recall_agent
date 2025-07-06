import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { Provider } from "react-redux" // 1. Import Provider from react-redux
import { store } from "@/store" 

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Provider store={store}> {/* 2. Wrap App with Provider and pass the store */}
      <App />
    </Provider>
  </StrictMode>,
)
