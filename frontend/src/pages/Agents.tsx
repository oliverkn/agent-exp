import React, { useEffect, useState } from 'react';
import axios from 'axios';

interface Thread {
  id: number;
  title: string;
  created_at: string;
}

interface Message {
  id: number;
  role: 'assistant' | 'tool' | 'user' | 'developer';
  content?: string;
  agent_state?: string;
  created_at: string;
  tool_name?: string;
  tool_call_id?: string;
  tool_result?: string;
}

export default function Agents() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [selectedThread, setSelectedThread] = useState<Thread | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [newThreadTitle, setNewThreadTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [newMessage, setNewMessage] = useState('');

  const API_BASE_URL = 'http://localhost:8000';

  useEffect(() => {
    fetchThreads();
  }, []);

  // Fetch messages when thread is selected
  useEffect(() => {
    if (selectedThread) {
      fetchThreadMessages(selectedThread.id);
    }
  }, [selectedThread]);

  useEffect(() => {
    let ws: WebSocket;
    let pingInterval: NodeJS.Timeout;
    
    if (selectedThread) {
        const wsUrl = API_BASE_URL.replace('http://', 'ws://');
        console.log('Attempting to connect to WebSocket:', `${wsUrl}/ws/${selectedThread.id}`);
        
        try {
            ws = new WebSocket(`${wsUrl}/ws/${selectedThread.id}`);
            
            ws.onopen = () => {
                console.log('WebSocket connected successfully');
                // Start ping-pong to keep connection alive
                pingInterval = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send('ping');
                    }
                }, 30000); // Send ping every 30 seconds
            };
            
            ws.onmessage = async (event) => {
                try {
                    console.log('Raw WebSocket message received:', event.data);
                    
                    // Skip parsing for ping-pong messages
                    if (event.data === 'pong') {
                        console.log('Received pong response');
                        return;
                    }
                    
                    const data = JSON.parse(event.data);
                    console.log('Parsed WebSocket data:', data);
                    
                    // Handle both "type" and "event_type" formats
                    const eventType = data.event_type || data.type;
                    
                    if (eventType === 'message_insert' && data.message) {
                        console.log('New message received, adding to UI:', data.message);
                        addMessage(data.message);
                    } else if (eventType === 'message_update' && data.message) {
                        console.log('Message update received, updating UI:', data.message);
                        updateMessage(data.message);
                    } else {
                        console.log('Unhandled WebSocket message type:', data);
                    }
                } catch (error) {
                    console.error('Error processing WebSocket message:', error);
                    console.error('Raw message that caused error:', event.data);
                }
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
            
            ws.onclose = (event) => {
                console.log('WebSocket disconnected:', event.code, event.reason);
            };
        } catch (error) {
            console.error('Error creating WebSocket connection:', error);
        }
    }

    return () => {
        if (pingInterval) {
            clearInterval(pingInterval);
        }
        if (ws) {
            console.log('Cleaning up WebSocket connection');
            ws.close();
        }
    };
  }, [selectedThread]);

  const fetchThreads = async () => {
    try {
      setIsLoading(true);
      const response = await axios.get(`${API_BASE_URL}/api/threads/list`);
      setThreads(response.data);
    } catch (error) {
      setError('Failed to fetch threads');
      console.error('Error fetching threads:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchThreadMessages = async (threadId: number) => {
    try {
        console.log('Fetching messages for thread:', threadId);
        const response = await axios.get(
            `${API_BASE_URL}/api/threads/${threadId}/get_thread_messages`
        );
        console.log('Received messages:', response.data);
        setMessages(response.data);
    } catch (error) {
        console.error('Error fetching messages:', error);
    }
  };

  const createThread = async () => {
    if (!newThreadTitle.trim()) {
      setError('Please enter a thread title');
      return;
    }

    try {
      setIsLoading(true);
      const response = await axios.post(`${API_BASE_URL}/api/threads/create`, {
        title: newThreadTitle
      });
      setThreads(prevThreads => [response.data, ...prevThreads]);
      setNewThreadTitle('');
    } catch (error) {
      setError('Failed to create thread');
      console.error('Error creating thread:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const sendMessage = async () => {
    if (!selectedThread || !newMessage.trim()) return;

    const messageContent = newMessage;
    setNewMessage('');
    setError(null); // Clear any previous errors

    try {
        const response = await axios.post(`${API_BASE_URL}/api/threads/${selectedThread.id}/message`, {
            content: messageContent
        });
        
        if (response.data.message) {
            setMessages(prevMessages => [...prevMessages, response.data.message]);
        }
    } catch (error: any) {
        console.error('Error sending message:', error);
        setNewMessage(messageContent);
        
        // Show user-friendly error message
        const errorMessage = error.response?.data?.detail || 
                           error.response?.data?.message || 
                           'Failed to send message. Please try again.';
        setError(errorMessage);
        
        // Optionally refresh messages to ensure consistency
        if (selectedThread) {
            await fetchThreadMessages(selectedThread.id);
        }
    }
  };

  const isAwaitingInput = messages.length > 0 && 
    messages[messages.length - 1].agent_state === 'await_input';

  const renderMessage = (message: Message) => {
    // Skip assistant messages that are tool calls
    if (message.role === 'assistant' && message.tool_call_id) {
      return null;
    }

    const messageClasses = {
      assistant: 'bg-blue-50 text-blue-800',
      tool: 'bg-green-50 text-green-800',
      user: 'bg-gray-50 text-gray-800',
      developer: 'bg-purple-50 text-purple-800'
    };

    return (
      <div className={`p-4 rounded-lg mb-4 ${messageClasses[message.role]}`}>
        <div className="font-medium capitalize">
          {message.role === 'tool' && message.tool_name 
            ? `${message.role} (${message.tool_name})`
            : message.role
          }
        </div>
        <div className="mt-2">
          {message.role === 'tool' ? (
            <>
              {message.content && (
                <div className="mb-2">
                  <span className="font-medium">Input: </span>
                  <ToolMessage message={message.content} />
                </div>
              )}
              {message.tool_result && (
                <div>
                  <span className="font-medium">Result: </span>
                  {message.tool_result}
                </div>
              )}
            </>
          ) : (
            message.content
          )}
        </div>
      </div>
    );
  };

  const addMessage = (msg: Message) => {
    setMessages(prevMessages => [...prevMessages, msg]);
  };

  const updateMessage = (updatedMsg: Message) => {
    setMessages(prevMessages => 
      prevMessages.map(msg => 
        msg.id === updatedMsg.id ? { ...msg, ...updatedMsg } : msg
      )
    );
  };

  const handleThreadSelect = async (thread: Thread) => {
    setSelectedThread(thread);
    setMessages([]); // Clear existing messages
    
    try {
        const response = await axios.get(
            `${API_BASE_URL}/api/threads/${thread.id}/get_thread_messages`
        );
        response.data.forEach((msg: Message) => {
            addMessage(msg);
        });
    } catch (error) {
        console.error('Error fetching messages:', error);
        setError('Failed to load messages');
    }
  };

  const renderThreadList = () => (
    <div className="space-y-2 overflow-y-auto">
      {threads.map((thread) => (
        <div
          key={thread.id}
          onClick={() => handleThreadSelect(thread)}
          className={`p-3 rounded-md cursor-pointer ${
            selectedThread?.id === thread.id
              ? 'bg-blue-100'
              : 'hover:bg-gray-100'
          }`}
        >
          <h3 className="font-medium">{thread.title}</h3>
          <p className="text-sm text-gray-500">
            {new Date(thread.created_at).toLocaleDateString()}
          </p>
        </div>
      ))}
    </div>
  );

  const ToolMessage = ({ message }: { message: string }) => {
    return (
      <div
        dangerouslySetInnerHTML={{
          __html: message
        }}
      />
    );
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Thread List Panel */}
      <div className="w-1/4 bg-white border-r border-gray-200 p-4 flex flex-col">
        <div className="mb-4">
          <input
            type="text"
            value={newThreadTitle}
            onChange={(e) => setNewThreadTitle(e.target.value)}
            placeholder="New Thread Title"
            className="w-full px-3 py-2 border border-gray-300 rounded-md mb-2"
          />
          <button
            onClick={createThread}
            disabled={isLoading}
            className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {isLoading ? 'Creating...' : 'Create Thread'}
          </button>
          {error && <div className="text-red-500 text-sm mt-2">{error}</div>}
        </div>

        {renderThreadList()}
      </div>

      {/* Messages Panel */}
      <div className="flex-1 flex flex-col">
        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4">
              {error}
            </div>
          )}
          {selectedThread ? (
            <div className="space-y-4">
              {messages.map((message, index) => (
                message && <div key={index}>{renderMessage(message)}</div>
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500">
              Select a thread to view messages
            </div>
          )}
        </div>

        {/* Message Input */}
        {selectedThread && (
          <div className="p-4 border-t border-gray-200 bg-white">
            <div className="flex space-x-4">
              <input
                type="text"
                value={newMessage}
                onChange={(e) => setNewMessage(e.target.value)}
                disabled={!isAwaitingInput}
                placeholder={isAwaitingInput ? "Type your message..." : "Waiting for AI..."}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                onKeyPress={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
              />
              <button
                onClick={sendMessage}
                disabled={!isAwaitingInput || !newMessage.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                Send
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
} 