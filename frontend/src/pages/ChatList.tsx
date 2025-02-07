import React, { useEffect, useState, useRef } from 'react';

interface Message {
  id: number;
  content: string;
  chat_id: number;
  created_at: string;
  is_user: boolean;
}

interface Chat {
  id: number;
  title: string;
  created_at: string;
  updated_at: string | null;
  messages?: Message[];
}

const ChatList: React.FC = () => {
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [chats, setChats] = useState<Chat[]>([]);
  const [newChatTitle, setNewChatTitle] = useState('');
  const [selectedChat, setSelectedChat] = useState<Chat | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetchChats();
  }, []);

  useEffect(() => {
    if (selectedChatId) {
      fetchChat(selectedChatId);
      fetchMessages(selectedChatId);
      connectWebSocket();
    }

    return () => {
      // Cleanup WebSocket connection when chat changes
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [selectedChatId]);

  const connectWebSocket = () => {
    if (!selectedChatId || wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    console.log(`Attempting to connect to WebSocket for chat ${selectedChatId}`);
    const ws = new WebSocket(`ws://localhost:8000/api/ws/${selectedChatId}`);

    ws.onopen = () => {
      console.log(`WebSocket Connected for chat ${selectedChatId}`);
      setError(null); // Clear any previous connection errors
    };

    ws.onmessage = (event) => {
      console.log('Received message:', event.data);
      try {
        const message = JSON.parse(event.data);
        setMessages(prev => [...prev, message]);
      } catch (e) {
        console.error('Error parsing message:', e);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setError('Connection error. Messages may not be real-time.');
    };

    ws.onclose = (event) => {
      console.log(`WebSocket disconnected for chat ${selectedChatId}. Code: ${event.code}, Reason: ${event.reason}`);
      // Only attempt to reconnect if the connection was previously established
      if (event.code !== 4004) { // 4004 is our custom code for "Chat not found"
        setTimeout(connectWebSocket, 3000);
      }
    };

    wsRef.current = ws;
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const fetchChats = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/chats/');
      if (response.ok) {
        const data = await response.json();
        setChats(data);
      }
    } catch (error) {
      console.error('Error fetching chats:', error);
    }
  };

  const fetchChat = async (id: number) => {
    setLoading(true);
    try {
      const response = await fetch(`http://localhost:8000/api/chats/${id}`);
      if (response.ok) {
        const data = await response.json();
        setSelectedChat(data);
      }
    } catch (error) {
      console.error('Error fetching chat:', error);
      setError('Failed to load chat');
    }
  };

  const fetchMessages = async (id: number) => {
    try {
      const response = await fetch(`http://localhost:8000/api/chats/${id}/messages/`);
      if (response.ok) {
        const data = await response.json();
        setMessages(data);
      }
    } catch (error) {
      console.error('Error fetching messages:', error);
      setError('Failed to load messages');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newChatTitle.trim()) return;

    try {
      const response = await fetch('http://localhost:8000/api/chats/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ title: newChatTitle }),
      });

      if (response.ok) {
        const chat = await response.json();
        setChats(prev => [...prev, chat]);
        setNewChatTitle('');
        setSelectedChatId(chat.id);
      }
    } catch (error) {
      console.error('Error creating chat:', error);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMessage.trim() || sendingMessage || !wsRef.current || !selectedChatId) return;

    setSendingMessage(true);
    setError(null);

    try {
      // Send message through WebSocket
      wsRef.current.send(JSON.stringify({
        content: newMessage
      }));
      
      setNewMessage('');
    } catch (error) {
      console.error('Error sending message:', error);
      setError('Failed to send message');
    } finally {
      setSendingMessage(false);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (date.toDateString() === yesterday.toDateString()) {
      return `Yesterday ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    } else {
      return date.toLocaleDateString([], { 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    }
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Chat List Sidebar */}
      <div className="w-80 bg-white border-r flex flex-col">
        <div className="p-4 border-b">
          <h1 className="text-xl font-bold mb-4">Chats</h1>
          <form onSubmit={handleCreateChat}>
            <div className="space-y-2">
              <input
                type="text"
                value={newChatTitle}
                onChange={(e) => setNewChatTitle(e.target.value)}
                placeholder="Enter chat title..."
                className="w-full p-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="submit"
                className="w-full px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 focus:outline-none focus:ring-2 focus:ring-green-500"
              >
                Create New Chat
              </button>
            </div>
          </form>
        </div>
        
        <div className="flex-1 overflow-y-auto">
          {chats.map((chat) => (
            <div
              key={chat.id}
              onClick={() => setSelectedChatId(chat.id)}
              className={`block p-4 border-b hover:bg-gray-50 transition-colors cursor-pointer ${
                selectedChatId === chat.id ? 'bg-blue-50' : ''
              }`}
            >
              <h2 className="font-semibold">{chat.title}</h2>
              <p className="text-sm text-gray-500">
                {new Date(chat.created_at).toLocaleDateString()}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Chat Area */}
      {selectedChatId ? (
        <div className="flex-1 flex flex-col">
          {/* Chat Header */}
          <div className="bg-white shadow-sm p-4">
            <h2 className="text-xl font-semibold">{selectedChat?.title}</h2>
            {error && <div className="text-red-500 text-sm mt-1">{error}</div>}
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {loading ? (
              <div className="flex justify-center items-center h-full">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
              </div>
            ) : (
              messages.map((message) => (
                <div key={message.id} className="flex items-start space-x-3">
                  <div 
                    className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                      message.is_user 
                        ? 'bg-blue-500 text-white'
                        : 'bg-gray-500 text-white'
                    }`}
                  >
                    {message.is_user ? 'U' : 'A'}
                  </div>
                  <div className="flex-1">
                    <p className="text-gray-800 break-words">{message.content}</p>
                    <span className="text-xs text-gray-500 block mt-1">
                      {formatTimestamp(message.created_at)}
                    </span>
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Message Input */}
          <form onSubmit={handleSendMessage} className="p-4 bg-white border-t">
            <div className="flex space-x-4">
              <input
                type="text"
                value={newMessage}
                onChange={(e) => setNewMessage(e.target.value)}
                placeholder="Type your message..."
                className="flex-1 p-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                disabled={sendingMessage}
              />
              <button
                type="submit"
                disabled={sendingMessage || !newMessage.trim()}
                className={`px-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 
                  ${sendingMessage || !newMessage.trim()
                    ? 'bg-gray-300 cursor-not-allowed'
                    : 'bg-blue-500 hover:bg-blue-600 text-white'
                  }`}
              >
                {sendingMessage ? 'Sending...' : 'Send'}
              </button>
            </div>
          </form>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-gray-500">
          Select a chat or create a new one to get started
        </div>
      )}
    </div>
  );
};

export default ChatList; 