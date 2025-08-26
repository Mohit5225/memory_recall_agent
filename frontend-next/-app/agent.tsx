import React, { useState, useEffect ,useRef } from 'react';
import { cn } from '@/lib/utils';

interface ChatMessage {
  sender: 'user' | 'assistant';
  text: string;
}

const AgentPage: React.FC = () => {
  const [darkMode, setDarkMode] = useState(false);
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [message, setMessage] = useState('');
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(false);
  const [rightSidebarOpen, setRightSidebarOpen] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' }); // <-- this scrolls to bottom
    }
  }, [chatHistory]); // <-- runs every time chatHistory changes

  // ...existing code...
  <div className="flex-1 w-full max-w-3xl overflow-y-auto bg-white dark:bg-gray-900 shadow-md rounded-lg p-4">
    {chatHistory.map((msg, idx) => (
      <div
        key={idx}
        className={cn(
          'p-2 rounded-lg mb-2',
          msg.sender === 'user' ? 'bg-blue-500 text-white self-end' : 'bg-gray-300 dark:bg-gray-700 text-black'
        )}
      >
        {msg.text}
      </div>
    ))}
    <div ref={chatEndRef} /> {/* <-- add this right after the map */}
  </div>
  useEffect(() => {
    // Fetch chat history from backend
    fetch('/api/chat/history')
      .then((res) => res.json())
      .then((data: ChatMessage[]) => setChatHistory(data))
      .catch(() => setChatHistory([]));
  }, []);

  const handleSendMessage = () => {
    if (!message.trim()) return;
    const newMessage: ChatMessage = { sender: 'user', text: message };
    setChatHistory((prev) => [...prev, newMessage]);
    setMessage('');
    // Reset textarea height after sending
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  // Auto-resize textarea as user types
  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const textarea = e.target;
    setMessage(textarea.value);
    
    // Reset height and calculate new height
    textarea.style.height = 'auto';
    const scrollHeight = textarea.scrollHeight;
    const maxHeight = 90; // About 3 rows max (40px per row)
    
    // Set height up to maxHeight, then enable scrolling
    textarea.style.height = Math.min(scrollHeight, maxHeight) + 'px';
    textarea.style.overflowY = scrollHeight > maxHeight ? 'auto' : 'hidden';
  };

  // Handle Enter key (send on Enter, new line on Shift+Enter)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className={cn(darkMode ? 'dark' : '', 'min-h-screen flex flex-col')}>      
      {/* Navbar */}
      <nav className="sticky top-0 z-10 bg-white dark:bg-gray-900 shadow-md flex justify-between items-center px-0.5 py-1">
        <div className="text-xl font-semibold">Memory Recaller Agent</div>
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setDarkMode(!darkMode)}
            className="p-2 rounded-full bg-gray-200 dark:bg-gray-700"
          >
            {darkMode ? 'Light Mode' : 'Dark Mode'}
          </button>
        </div>
      </nav>

      <div className="flex flex-1">
        {/* Left Sidebar */}
        <aside
          className={cn(
            'bg-gray-100 dark:bg-gray-800 p-4 w-64',
            leftSidebarOpen ? 'block' : 'hidden'
          )}
        >
          <h2 className="text-lg font-semibold mb-4">Memory Slots</h2>
          {/* Add memory slots here */}
        </aside>

        {/* Main Chat Interface */}
        <main className="flex-1 flex flex-col items-center justify-between p-4">
          <div className="flex-1 w-full max-w-3xl overflow-y-auto bg-white dark:bg-gray-900 shadow-md rounded-lg p-4">
            {chatHistory.map((msg, idx) => (
              <div
                key={idx}
                className={cn(
                  'p-2 rounded-lg mb-2',
                  msg.sender === 'user' ? 'bg-blue-500 text-white self-end' : 'bg-gray-300 dark:bg-gray-700 text-black'
                )}
              >
                {msg.text}
              </div>
            ))}
          </div>
          <div className="w-full max-w-3xl flex items-end mt-4">
            <textarea
              ref={textareaRef}
              value={message}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask about React, state management, etc."
              className="flex-1 p-2 border rounded-l-lg dark:bg-gray-800 dark:text-white resize-none overflow-y-hidden min-h-[40px] max-h-[90px]"
              rows={1}
            />
            <button
              onClick={handleSendMessage}
              className="p-2 bg-blue-500 text-white rounded-r-lg h-[40px] flex items-center justify-center"
            >
              Send
            </button>
          </div>
        </main>

        {/* Right Sidebar */}
        <aside
          className={cn(
            'bg-gray-100 dark:bg-gray-800 p-4 w-64',
            rightSidebarOpen ? 'block' : 'hidden'
          )}
        >
          <h2 className="text-lg font-semibold mb-4">Custom Instructions</h2>
          <textarea
            className="w-full p-2 border rounded-lg dark:bg-gray-800 dark:text-white"
            placeholder="Add custom instructions for the chatbot"
          />
        </aside>
      </div>
    </div>
  );
};

export default AgentPage 