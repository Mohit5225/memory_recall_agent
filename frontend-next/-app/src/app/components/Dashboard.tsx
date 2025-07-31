import React, { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Menu, X, Settings, PlusCircle, Search, BookOpen, Rocket, Send } from 'lucide-react';
import ChatHistory from './ChatHistory';
import { RootState } from '../store';
import { useSelector } from 'react-redux';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}


const Dashboard: React.FC = () => {
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(false);
  const [rightSidebarOpen, setRightSidebarOpen] = useState(false);
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [message, setMessage] = useState('');
  const [memorySlots, setMemorySlots] = useState<string[]>(['React Router', 'State Management']);
  const [searchQuery, setSearchQuery] = useState('');
  const [customInstructions, setCustomInstructions] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiValidation, setApiValidation] = useState<'valid' | 'invalid' | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const userId = useSelector((state: RootState) => state.auth.user?.user_id);
  
 

useEffect(() => {
  console.log("Dashboard useEffect triggered - userId:", userId);
  
  const fetchChatHistory = async () => {
    console.log("fetchChatHistory called, userId:", userId);

    if (!userId) {
      console.log("No userId found, skipping fetch");
      return;
    }
    try {
      setIsLoading(true);
      console.log("Making fetch request to chat history API");
      const response = await fetch('http://localhost:8000/api/v1/chat/history', {
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
        }
      });
      console.log("Response status:", response.status);

      if (!response.ok) {
        throw new Error('Failed to fetch chat history');
      }

      const data = await response.json();
      console.log("Fetched messages:", data);
      console.log("Data length:", data.length);
      console.log("First message:", data[0]);
      // Use backend data directly since it now has correct role/content format
      setChatHistory(data);
      console.log("Chat history state updated");
    } catch (error) {
      console.error('Failed to fetch chat history:', error);
      setChatHistory([]);
    } finally {
      setIsLoading(false);
    }
  };

  fetchChatHistory();
}, [userId]);

const handleSendMessage = async () => {
  if (!message.trim()) return;
  setIsLoading(true);
  
  const newMessage = { role: 'user' as const, content: message };
  setChatHistory(prev => [...prev, newMessage]);
  setMessage('');

  try {
    const response = await fetch('http://localhost:8000/api/v1/chat', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: message,
        user_id: userId,
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to send message');
    }

    const data = await response.json();
    setChatHistory(prev => [...prev, {
      role: 'assistant',
      content: data.response
    }]);
  } catch (error) {
    console.error('Failed to send message:', error);
  } finally {
    setIsLoading(false);
  }
};
  const handleNewChat = () => {
    console.log("New chat triggered - clearing chat history");
    setChatHistory([]);
    setMessage('');
  };

  const filteredMemorySlots = memorySlots.filter((slot) =>
    slot.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const addMemorySlot = (topic: string) => {
    if (topic.trim() && !memorySlots.includes(topic.trim())) {
      setMemorySlots([...memorySlots, topic.trim()]);
    }
  };

  const removeMemorySlot = (topic: string) => {
    setMemorySlots(memorySlots.filter((slot) => slot !== topic));
  };

  const validateApiKey = () => {
    fetch('/api/validate-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ apiKey }),
    })
      .then((res) => (res.ok ? setApiValidation('valid') : setApiValidation('invalid')))
      .catch(() => setApiValidation('invalid'));
  };

  // Custom Logo SVG
  // Deep Space palette: Nebula Purple gradients, Lunar White glow
  const AppLogo = () => (
    <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Outer interlocking ring */}
      <path
        d="M20 6
           a14 14 0 1 1 0 28
           a14 14 0 1 1 0-28"
        fill="none"
        stroke="url(#ringGradient)"
        strokeWidth="3.5"
        strokeLinecap="round"
        filter="url(#ringGlow)"
      />
      {/* Interlocking chat bubble left */}
      <path
        d="M13 20
           a7 7 0 1 1 14 0
           a7 7 0 1 1 -14 0"
        fill="none"
        stroke="url(#bubbleLeft)"
        strokeWidth="2.2"
        strokeLinecap="round"
        filter="url(#bubbleGlow)"
      />
      {/* Interlocking chat bubble right */}
      <path
        d="M27 20
           a7 7 0 1 0 -14 0
           a7 7 0 1 0 14 0"
        fill="none"
        stroke="url(#bubbleRight)"
        strokeWidth="2.2"
        strokeLinecap="round"
        filter="url(#bubbleGlow)"
      />
      {/* Message tail */}
      <path
        d="M20 27
           Q22 32 28 32"
        stroke="url(#tailGradient)"
        strokeWidth="1.2"
        fill="none"
        strokeLinecap="round"
      />
      {/* Central glowing dot */}
      <circle cx="20" cy="20" r="3.5" fill="url(#dotGradient)" />
      <defs>
        {/* Outer ring: Nebula Purple to lighter purple */}
        <linearGradient id="ringGradient" x1="6" y1="6" x2="34" y2="34" gradientUnits="userSpaceOnUse">
          <stop stopColor="#7C3AED"/>
          <stop offset="1" stopColor="#9575CD"/>
        </linearGradient>
        {/* Left bubble: Nebula Purple to Meteor Gray */}
        <linearGradient id="bubbleLeft" x1="13" y1="13" x2="27" y2="27" gradientUnits="userSpaceOnUse">
          <stop stopColor="#7C3AED"/>
          <stop offset="1" stopColor="#4B5563"/>
        </linearGradient>
        {/* Right bubble: lighter purple to Nebula Purple */}
        <linearGradient id="bubbleRight" x1="27" y1="13" x2="13" y2="27" gradientUnits="userSpaceOnUse">
          <stop stopColor="#9575CD"/>
          <stop offset="1" stopColor="#7C3AED"/>
        </linearGradient>
        {/* Tail: Nebula Purple to lighter purple */}
        <linearGradient id="tailGradient" x1="20" y1="27" x2="28" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="#7C3AED"/>
          <stop offset="1" stopColor="#9575CD"/>
        </linearGradient>
        {/* Dot: Lunar White to Nebula Purple */}
        <radialGradient id="dotGradient" cx="0.5" cy="0.5" r="0.5" fx="0.6" fy="0.4">
          <stop offset="0%" stopColor="#F1F5F9"/>
          <stop offset="100%" stopColor="#7C3AED"/>
        </radialGradient>
        <filter id="ringGlow" x="0" y="0" width="40" height="40">
          <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
          <feMerge>
            <feMergeNode in="coloredBlur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
        <filter id="bubbleGlow" x="0" y="0" width="40" height="40">
          <feGaussianBlur stdDeviation="1" result="coloredBlur"/>
          <feMerge>
            <feMergeNode in="coloredBlur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>
    </svg>
  );

  return (
    <div className="min-h-screen flex bg-[#1A1A1A] text-[#F1F5F9]/98">
      {/* Left Sidebar */}
      <aside
        className={cn(
          // Sidebar: Deep Space Black gradient, border Meteor Gray, text Lunar White
          'fixed top-0 left-0 h-full w-[35vw] bg-gradient-to-b from-[#1A1A1A] to-[#2D2D2D] text-[#F1F5F9] p-4 z-30 transition-all duration-300 backdrop-blur-md border-r border-[#4B5563] shadow-2xl',
          leftSidebarOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center space-x-2">
            <AppLogo />
            <span className="text-xl font-bold text-[#F1F5F9]">Memory Recaller</span>
          </div>
          <button 
            onClick={() => setLeftSidebarOpen(false)}
            className="text-[#4B5563] hover:text-[#7C3AED] transition-colors duration-200"
          >
            <X size={24} />
          </button>
        </div>
        <button
          onClick={handleNewChat}
          // New Chat: Nebula Purple bg, Lunar White text, hover lighter purple
          className="flex items-center w-full p-3 bg-[#7C3AED] text-[#F1F5F9] rounded-lg hover:bg-[#9575CD] transition-all duration-200 mb-4 shadow-lg"
        >
          <PlusCircle size={20} className="mr-2" /> New Chat
        </button>
        <div className="relative mb-4">
          <Search size={20} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-[#4B5563]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search memory slots"
            // Search Input: Deep Space Black bg, Meteor Gray border, Lunar White placeholder at 50%, Nebula Purple focus
            className="w-full pl-10 p-3 bg-[#1A1A1A] rounded-lg border border-[#4B5563] focus:outline-none focus:ring-2 focus:ring-[#7C3AED]/50 focus:border-transparent text-[#F1F5F9] placeholder-[#F1F5F9]/50 shadow-inner transition-all duration-200"
          />
        </div>
        <h3 className="text-sm font-semibold mb-3 text-[#F1F5F9] uppercase tracking-wide">Library</h3>
        <div className="space-y-2 mb-4 max-h-[40vh] overflow-y-auto">
          {filteredMemorySlots.map((slot) => (
            <div
              key={slot}
              // Memory Slot Card: Meteor Gray bg/border, hover Nebula Purple at 10%, Lunar White text, Nebula Purple remove
              className="flex justify-between items-center p-3 bg-[#4B5563] rounded-lg hover:bg-[#7C3AED]/10 cursor-pointer transition-all duration-200 border border-[#4B5563] shadow-sm"
            >
              <span 
                onClick={() => setMessage(slot)}
                className="text-[#F1F5F9] hover:text-[#7C3AED] transition-colors duration-200"
              >
                {slot}
              </span>
              <button 
                onClick={() => removeMemorySlot(slot)} 
                className="text-[#7C3AED] hover:text-[#9575CD] transition-colors duration-200"
              >
                ✕
              </button>
            </div>
          ))}
          <input
            type="text"
            placeholder="Add topic"
            // Add topic input: Deep Space Black bg, Meteor Gray border, Lunar White placeholder at 50%, Nebula Purple focus
            className="w-full p-3 bg-[#1A1A1A] rounded-lg border border-[#4B5563] focus:outline-none focus:ring-2 focus:ring-[#7C3AED]/50 focus:border-transparent text-[#F1F5F9] placeholder-[#F1F5F9]/50 transition-all duration-200"
            onKeyPress={(e) => e.key === 'Enter' && addMemorySlot(e.currentTarget.value)}
          />
        </div>
        <button className="w-full p-3 bg-[#FFC107] text-[#F1F5F9] rounded-lg hover:bg-[#FFB300] flex items-center justify-center transition-all duration-200 shadow-lg">
          <Rocket size={20} className="mr-2" /> Upgrade Plan
        </button>
      </aside>

      {/* Main Chat Area */}
      <div
        className={cn(
          'flex-1 flex flex-col transition-all duration-300',
          leftSidebarOpen && 'ml-[35vw]'
        )}
      >
        {/* Navbar */}
        <nav className="sticky top-0 z-20 bg-[#1A1A1A] p-4 flex justify-between items-center border-b border-[#4B5563] shadow-lg">
          <button
            onClick={() => setLeftSidebarOpen(!leftSidebarOpen)}
            className="flex items-center space-x-2 hover:opacity-80 transition-opacity duration-200"
          >
            <AppLogo />
            <span className="text-xl font-bold text-[#F1F5F9]">Memory Recaller</span>
          </button>
          <button
            onClick={() => setRightSidebarOpen(!rightSidebarOpen)}
            // Settings: Nebula Purple icon, hover Nebula Purple at 20% bg
            className="text-[#7C3AED] hover:bg-[#7C3AED]/20 rounded-full p-2 transition-colors duration-200"
          >
            <Settings size={24} />
          </button>
        </nav>

        {/* Chat Content */}
        <ChatHistory
          messages={chatHistory}
          isLoading={isLoading}
          className="flex-1 bg-[#1A1A1A] rounded-lg overflow-y-auto"
        />

        {/* Input Area */}
        <div className="p-4 bg-[#1A1A1A] sticky bottom-0 border-t border-[#5F6483] shadow-lg">
          <div className="w-full flex items-center max-w-3xl mx-auto">
            <input
              type="text"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Ask anything..."
              // Input: Deep Space Black bg, Cosmic Gray border, Lunar White placeholder at 50%, Misty Nebula focus
              className="flex-1 p-3 bg-[#1A1A1A] rounded-l-lg border border-[#5F6483] focus:outline-none focus:ring-2 focus:ring-[#9575CD]/50 focus:border-transparent text-[#F1F5F9]/98 placeholder:text-[#F1F5F9]/50 transition-all duration-200"
              onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
            />
            <button
              onClick={handleSendMessage}
              className="p-3 bg-gradient-to-b from-[#7C3AED] to-[#5F6483] rounded-r-lg hover:opacity-90 hover:blur-[0.2px] transition-all duration-200 shadow-lg"
            >
              <Send size={20} className="text-[#F1F5F9]" />
            </button>
          </div>
        </div>
      </div>

      {/* Right Sidebar */}
      <aside
        className={cn(
          // Settings Sidebar: Deep Space Black gradient, border Meteor Gray, text Lunar White
          'fixed top-0 right-0 h-full w-[35vw] bg-gradient-to-b from-[#1A1A1A] to-[#2D2D2D] text-[#F1F5F9] p-4 z-30 transition-all duration-300 backdrop-blur-md border-l border-[#4B5563] shadow-2xl',
          rightSidebarOpen ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        <div className="flex justify-between items-center mb-6">
          <div className="text-xl font-bold text-[#F1F5F9]">Settings</div>
          <button 
            onClick={() => setRightSidebarOpen(false)}
            className="text-[#4B5563] hover:text-[#7C3AED] transition-colors duration-200"
          >
            <X size={24} />
          </button>
        </div>
        <h2 className="text-lg font-semibold mb-4 text-[#F1F5F9] uppercase tracking-wide">Custom Instructions</h2>
        <textarea
          value={customInstructions}
          onChange={(e) => setCustomInstructions(e.target.value)}
          placeholder="How should I respond?"
          // Textarea: Deep Space Black bg, Meteor Gray border, Lunar White placeholder at 50%, Nebula Purple focus
          className="w-full p-3 bg-[#1A1A1A] rounded-lg border border-[#4B5563] focus:outline-none focus:ring-2 focus:ring-[#7C3AED]/50 focus:border-transparent text-[#F1F5F9] placeholder-[#F1F5F9]/50 min-h-[150px] resize-y transition-all duration-200"
        />
        <h3 className="text-sm font-semibold mt-6 mb-3 text-[#F1F5F9] uppercase tracking-wide">API Settings</h3>
        <input
          type="text"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="Enter API key"
          // API Key Input: Deep Space Black bg, Meteor Gray border, Lunar White placeholder at 50%, Nebula Purple focus
          className="w-full p-3 bg-[#1A1A1A] rounded-lg border border-[#4B5563] focus:outline-none focus:ring-2 focus:ring-[#7C3AED]/50 focus:border-transparent text-[#F1F5F9] placeholder-[#F1F5F9]/50 transition-all duration-200"
        />
        <button
          onClick={validateApiKey}
          // Validate Button: Nebula Purple to lighter purple gradient, hover Nebula Purple at 80%
          className="w-full p-3 mt-3 bg-gradient-to-r from-[#7C3AED] to-[#9575CD] text-[#F1F5F9] rounded-lg hover:bg-[#7C3AED]/80 transition-all duration-200 shadow-lg"
        >
          Validate Key
        </button>
        {apiValidation === 'valid' && (
          // Success Alert: bg custom green at 20%, border custom green, Lunar White text
          <div className="text-[#F1F5F9] mt-3 p-2 bg-[#2E7D32]/20 rounded-lg border border-[#2E7D32]">
            Key validated!
          </div>
        )}
        {apiValidation === 'invalid' && (
          // Error Alert: bg custom red at 20%, border custom red, Lunar White text
          <div className="text-[#F1F5F9] mt-3 p-2 bg-[#B71C1C]/20 rounded-lg border border-[#B71C1C]">
            Invalid key!
          </div>
        )}
      </aside>
    </div>
  );
};

export default Dashboard;